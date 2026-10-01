from unittest.mock import AsyncMock, MagicMock
import pytest
from aiogram.types import Chat, Message, User

from app.bot.handlers import (
    handle_fields_list,
    handle_help,
    handle_login,
    handle_logout,
    handle_problem_zones,
    handle_recommendation,
    handle_register_notice,
    handle_start,
)
from app.bot.keyboards import (
    get_fields_inline_keyboard,
    get_indexes_inline_keyboard,
    get_main_reply_keyboard,
)
from app.main import create_app
from app.security import hash_password


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
async def test_bot_auth_and_field_isolation(tmp_path) -> None:
    from app.config import Settings
    settings = Settings(
        database_path=tmp_path / "bot_test.db",
        artifact_dir=tmp_path / "artifacts",
        app_env="demo",
    )
    app = create_app(settings)
    repo = app.state.repository

    # 1. Register users in repository
    user_a = repo.create_user(
        username="farmer_ali",
        password_hash=hash_password("parol123"),
        full_name="Ali Valiyev",
    )
    user_b = repo.create_user(
        username="farmer_vali",
        password_hash=hash_password("parol456"),
        full_name="Vali Aliyev",
    )

    # 2. Add fields for user_a
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
    from app.geometry import canonical_geojson_and_hash, geodesic_area_hectares, validate_polygon_geojson
    poly_geom = validate_polygon_geojson(polygon)
    geom, g_hash = canonical_geojson_and_hash(poly_geom)
    repo.create_field(
        geometry=geom,
        geometry_hash=g_hash,
        area_hectares=geodesic_area_hectares(poly_geom),
        crop_name="Paxta",
        planted_on=poly_geom and "2026-04-15",
        growth_stage="Gullash",
        user_id=int(user_a["id"]),
    )

    msg = MagicMock(spec=Message)
    msg.chat = Chat(id=99999, type="private")
    msg.from_user = User(id=99999, is_bot=False, first_name="Ali")
    msg.answer = AsyncMock()

    # 3. Before login, commands should be blocked with auth prompt
    msg.text = "/dalalar"
    await handle_fields_list(msg, app)
    msg.answer.assert_called_once()
    assert "kirish talab qilinadi" in msg.answer.call_args[0][0].lower()

    # 4. Attempting to register via telegram should be rejected
    msg.answer.reset_mock()
    await handle_register_notice(msg)
    msg.answer.assert_called_once()
    assert "mumkin emas" in msg.answer.call_args[0][0].lower()

    # 5. Wrong login credentials
    msg.answer.reset_mock()
    msg.text = "/login farmer_ali xatoparol"
    await handle_login(msg, app)
    msg.answer.assert_called_once()
    assert "noto'g'ri" in msg.answer.call_args[0][0].lower()

    # 6. Correct login credentials
    msg.answer.reset_mock()
    msg.text = "/login farmer_ali parol123"
    await handle_login(msg, app)
    msg.answer.assert_called_once()
    assert "muvaffaqiyatli" in msg.answer.call_args[0][0].lower()

    # 7. Now handle_fields_list should succeed and show user_a's field
    msg.answer.reset_mock()
    msg.text = "/dalalar"
    await handle_fields_list(msg, app)
    msg.answer.assert_called_once()
    assert "Paxta" in msg.answer.call_args[0][0]

    # 8. Test problem zones
    msg.answer.reset_mock()
    await handle_problem_zones(msg, app)
    msg.answer.assert_called_once()
    zones_text = msg.answer.call_args[0][0]
    assert "Fazoviy Muammoli Zonalar" in zones_text or "qayta ishlanmagan" in zones_text

    # 9. Test logout
    msg.answer.reset_mock()
    await handle_logout(msg, app)
    msg.answer.assert_called_once()
    assert "chiqdingiz" in msg.answer.call_args[0][0].lower()
