from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.ai import AIResult
from app.config import Settings
from app.db import Database
from app.main import create_app
from app.repository import Repository


def test_repository_chat_and_summary(tmp_path: Path) -> None:
    db = Database(tmp_path / "chat.db")
    db.initialize()
    repo = Repository(db)

    # 1. Create Field
    polygon = {
        "type": "Polygon",
        "coordinates": [
            [
                [68.50, 40.50],
                [68.51, 40.50],
                [68.51, 40.51],
                [68.50, 40.51],
                [68.50, 40.50],
            ]
        ],
    }
    field = repo.create_field(
        geometry=polygon,
        geometry_hash="dummy_hash_1",
        area_hectares=10.5,
        crop_name="Paxta",
        planted_on=date(2026, 4, 15),
        growth_stage="Gullash",
    )
    field_id = int(field["id"])

    # 2. Add chat messages
    msg1 = repo.add_chat_message(field_id, "user", "NDVI ko'rsatkichi nima uchun past?")
    assert msg1["role"] == "user"
    assert "NDVI" in msg1["content"]

    msg2 = repo.add_chat_message(
        field_id,
        "assistant",
        "NDVI tuproq namligi yoki ozuqa yetishmasligidan pasaygan.",
        rag_sources=[{"document_name": "AgroBook.pdf", "page_number": 12, "score": 0.85}],
    )
    assert msg2["role"] == "assistant"
    assert msg2["rag_sources"] is not None

    messages = repo.list_chat_messages(field_id)
    assert len(messages) == 2

    # 3. Upsert summary
    summary_text = "[Xabar #1, 2026-08-16 10:00] Foydalanuvchi NDVI haqida so'radi -> Tuproq namligi tekshirilishi tavsiya etildi."
    saved_summary = repo.upsert_chat_summary(
        field_id=field_id,
        summary_text=summary_text,
        message_count=2,
        last_message_id=int(msg2["id"]),
    )
    assert saved_summary["message_count"] == 2
    assert "Foydalanuvchi" in saved_summary["summary_text"]

    fetched_summary = repo.get_chat_summary(field_id)
    assert fetched_summary is not None
    assert fetched_summary["summary_text"] == summary_text


def test_chat_endpoint_with_rag_and_summary(tmp_path: Path) -> None:
    settings = Settings(
        app_env="demo",
        database_path=tmp_path / "chat_api.db",
        artifact_dir=tmp_path / "artifacts",
        openai_api_key="sk-fake-test-key",
    )
    app = create_app(settings)
    with TestClient(app) as client:
        # 1. Create Field
        polygon = {
            "type": "Polygon",
            "coordinates": [
                [
                    [68.50, 40.50],
                    [68.51, 40.50],
                    [68.51, 40.51],
                    [68.50, 40.51],
                    [68.50, 40.50],
                ]
            ],
        }
        field_resp = client.post(
            "/api/fields",
            json={
                "geometry": polygon,
                "crop_name": "Paxta",
                "planted_on": "2026-04-15",
                "growth_stage": "Gullash",
            },
        )
        field_id = field_resp.json()["id"]

        # 2. Add fake acquisition & recommendation
        with app.state.repository.database.connect() as conn:
            cur = conn.execute(
                """INSERT INTO acquisitions(field_id, acquired_at, product_id, revision_key, source_metadata_json, created_at)
                VALUES (?, datetime('now'), 'S2A_TEST', 'rev1', '{}', datetime('now'))""",
                (field_id,),
            )
            acq_id = int(cur.lastrowid or 0)
            conn.execute(
                """INSERT INTO recommendations(field_id, acquisition_id, content, advice_json, model_name, created_at)
                VALUES (?, ?, 'Sugorish zarur', '{"red":[],"yellow":[],"green":[]}', 'test-ai', datetime('now'))""",
                (field_id, acq_id),
            )

        # Mock AI responses
        mock_ai = AsyncMock()
        mock_ai.chat.return_value = AIResult(
            content="Paxtaga azotli o'g'it berish va sug'orish tavsiya qilinadi.",
            model_name="gpt-5.4-nano",
        )
        mock_ai.generate_summary.return_value = (
            "[Xabar #1, 2026-08-16 10:00]: O'g'it va sug'orish tavsiya qilindi."
        )
        app.state.ai = mock_ai

        chat_resp = client.post(
            f"/api/fields/{field_id}/chat",
            json={
                "messages": [{"role": "user", "content": "Paxtaga qanday o'g'it berish kerak?"}],
                "language": "uz-latn",
            },
        )
        assert chat_resp.status_code == 200
        res_data = chat_resp.json()
        assert "azotli" in res_data["answer"]
        assert res_data["summary"] is not None

        # Verify history endpoint
        hist_resp = client.get(f"/api/fields/{field_id}/chat/history")
        assert hist_resp.status_code == 200
        assert len(hist_resp.json()) == 2

        # Verify summary endpoint
        sum_resp = client.get(f"/api/fields/{field_id}/chat/summary")
        assert sum_resp.status_code == 200
        assert sum_resp.json() is not None
