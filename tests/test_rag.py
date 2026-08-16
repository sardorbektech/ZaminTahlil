from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from pypdf import PageObject, PdfWriter

from app.config import Settings
from app.db import Database
from app.main import create_app
from app.rag import RAGService


def create_sample_pdf(file_path: Path) -> None:
    writer = PdfWriter()
    page = PageObject.create_blank_page(width=300, height=300)
    writer.add_page(page)
    with open(file_path, "wb") as f:
        writer.write(f)


def test_rag_chunking() -> None:
    service = RAGService()
    text = "Paxta yetishtirishda suv rejimi juda muhim. G'o'za gullash davrida ko'p suv talab qiladi. Defoliatsiya sentabr oyida amalga oshiriladi."
    chunks = service.chunk_text(text, chunk_size=60, overlap=10)
    assert len(chunks) >= 1
    for c in chunks:
        assert len(c) > 0


def test_rag_ingest_and_search(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db_path = tmp_path / "rag_test.db"
    db = Database(db_path)
    db.initialize()

    # Manual insert sample text chunks to test search & terminal logging directly
    service = RAGService(similarity_threshold=0.40)
    doc_name = "Paxtachilik Qollanmasi"
    sample_texts = [
        "G'o'zada vilt kasalligi paydo bo'lganda barglar sarg'ayadi va ildiz qorayadi.",
        "Bug'doy ekish uchun maqbul muddat oktabr oyining birinchi o'n kunligidir.",
        "Azotli o'g'itlar vegetatsiya davrining boshida berilishi kerak.",
    ]
    embeddings = service.embed_texts(sample_texts)

    with db.connect() as conn:
        cursor = conn.execute(
            """INSERT INTO rag_documents(name, file_path, file_hash, total_pages, chunk_count, created_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'))""",
            (doc_name, "C:/test.pdf", "hash123", 1, len(sample_texts)),
        )
        doc_id = int(cursor.lastrowid or 0)
        for idx, (txt, emb) in enumerate(zip(sample_texts, embeddings, strict=True)):
            conn.execute(
                """INSERT INTO rag_chunks(document_id, page_number, chunk_index, chunk_text, embedding)
                VALUES (?, ?, ?, ?, ?)""",
                (doc_id, 1, idx, txt, emb.astype(np.float32).tobytes()),
            )

    # 1. Search for disease topic
    query = "G'o'za barglari sarg'ayishi va vilt kasalligi"
    results = service.search(query, database=db, top_k=2)

    captured = capsys.readouterr()
    assert "[RAG QIDIRUV]" in captured.out
    assert "G'o'za barglari sarg'ayishi" in captured.out
    assert len(results) >= 1
    assert "vilt" in results[0].text

    # 2. Search with low relevance (should trigger fallback log)
    irrelevant_query = "Kvant fizikasi va kosmik stansiyalar"
    low_results = service.search(irrelevant_query, database=db, threshold=0.95)
    captured2 = capsys.readouterr()
    assert len(low_results) == 0
    assert "[RAG MANBASI YETARLI EMAS]" in captured2.out


def test_rag_api_endpoints(tmp_path: Path) -> None:
    settings = Settings(
        app_env="demo",
        database_path=tmp_path / "rag_api.db",
        artifact_dir=tmp_path / "artifacts",
    )
    app = create_app(settings)
    with TestClient(app) as client:
        # List documents (initially empty)
        res = client.get("/api/rag/documents")
        assert res.status_code == 200
        assert res.json() == []
