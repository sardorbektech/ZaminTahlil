from unittest.mock import AsyncMock, MagicMock
import pytest
from aiogram.types import Chat, Message, User

from app.bot.handlers import (
    handle_fields_list,
    handle_help,
    handle_problem_zones,
    handle_recommendation,
    handle_start,
)
from app.bot.keyboards import (
    get_fields_inline_keyboard,
    get_indexes_inline_keyboard,
    get_main_reply_keyboard,
)
from app.main import create_app


def test_keyboards() -> None:
    kb_main = get_main_reply_keyboard()
    assert len(kb_main.keyboard) >= 4

    fields = [
        {"id": 1, "crop_name": "Paxta", "area_hectares": 12.5},
        {"id": 2, "crop_name": "Bug'doy", "area_hectares": 30.0},
    ]
    kb_fields = get_fields_inline_keyboard(fields, active_field_id=1)
    assert len(kb_fields.inline_keyboard) == 2
    assert "✅" in kb_fields.inline_keyboard[0][0].text

    kb_idx = get_indexes_inline_keyboard(1)
    assert len(kb_idx.inline_keyboard) == 3


@pytest.mark.asyncio
async def test_bot_start_and_help(tmp_path) -> None:
    app = create_app()

    msg = MagicMock(spec=Message)
    msg.chat = Chat(id=12345, type="private")
    msg.from_user = User(id=12345, is_bot=False, first_name="Ali")
    msg.answer = AsyncMock()

    await handle_start(msg, app)
    msg.answer.assert_called_once()
    start_text = msg.answer.call_args[0][0]
    assert "ZaminTahlil" in start_text

    msg.answer.reset_mock()
    await handle_help(msg)
    msg.answer.assert_called_once()
    help_text = msg.answer.call_args[0][0]
    assert "/dalalar" in help_text
    assert "/muammolar" in help_text
    assert "/hosil" in help_text


@pytest.mark.asyncio
async def test_bot_fields_and_problem_zones(tmp_path) -> None:
    from app.config import Settings
    settings = Settings(
        database_path=tmp_path / "bot_test.db",
        artifact_dir=tmp_path / "artifacts",
        app_env="demo",
    )
    app = create_app(settings)


    # Add a field to repository
    polygon = {
        "type": "Polygon",
        "coordinates": [
            [
                [69.20, 41.20],
                [69.21, 41.20],
                [69.21, 41.21],
                [69.20, 41.21],
                [69.20, 41.20],
            ]
        ],
    }
    from starlette.testclient import TestClient
    client = TestClient(app)
    field_resp = client.post(
        "/api/fields",
        json={
            "geometry": polygon,
            "crop_name": "Paxta",
            "planted_on": "2026-04-15",
            "growth_stage": "Gullash",
        },
    )
    assert field_resp.status_code == 201
    field_id = field_resp.json()["id"]


    msg = MagicMock(spec=Message)
    msg.chat = Chat(id=99999, type="private")
    msg.from_user = User(id=99999, is_bot=False, first_name="Vali")
    msg.answer = AsyncMock()

    # Test list fields
    await handle_fields_list(msg, app)
    msg.answer.assert_called_once()
    assert "Paxta" in msg.answer.call_args[0][0]

    # Test problem zones
    msg.answer.reset_mock()
    await handle_problem_zones(msg, app)
    msg.answer.assert_called_once()
    zones_text = msg.answer.call_args[0][0]
    assert "Fazoviy Muammoli Zonalar" in zones_text or "qayta ishlanmagan" in zones_text
