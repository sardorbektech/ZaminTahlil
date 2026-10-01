from pathlib import Path
import httpx
import pytest

from app.config import Settings
from app.db import Database
from app.main import app
from app.rendering import ArtifactWriter
from app.repository import Repository


@pytest.mark.asyncio
async def test_auth_registration_login_and_field_isolation(
    tmp_path: Path, polygon_geojson: dict[str, object]
) -> None:
    database = Database(tmp_path / "auth_test.sqlite3")
    database.initialize()
    app.state.repository = Repository(database)
    app.state.artifact_writer = ArtifactWriter(tmp_path / "artifacts")
    app.state.settings = Settings(
        database_path=tmp_path / "auth_test.sqlite3",
        artifact_dir=tmp_path / "artifacts",
        sentinel_hub_client_id=None,
        sentinel_hub_client_secret=None,
    )
    app.state.ai = None
    app.state.sentinel = None

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Register User 1
        reg_resp = await client.post(
            "/api/auth/register",
            json={
                "username": "sardorbek",
                "password": "strongpassword123",
                "full_name": "Sardorbek Rahimov",
            },
        )
        assert reg_resp.status_code == 201
        data1 = reg_resp.json()
        assert "token" in data1
        assert data1["user"]["username"] == "sardorbek"
        token1 = data1["token"]

        # 2. Duplicate registration should fail
        dup_resp = await client.post(
            "/api/auth/register",
            json={
                "username": "sardorbek",
                "password": "anotherpassword",
            },
        )
        assert dup_resp.status_code == 409

        # 3. Login User 1
        login_resp = await client.post(
            "/api/auth/login",
            json={
                "username": "sardorbek",
                "password": "strongpassword123",
            },
        )
        assert login_resp.status_code == 200
        assert "token" in login_resp.json()

        # 4a. Non-existent user login -> specific "akkaunt topilmadi" error
        not_found_login = await client.post(
            "/api/auth/login",
            json={
                "username": "mavjud_emas_user",
                "password": "somepassword123",
            },
        )
        assert not_found_login.status_code == 401
        assert "akkaunt topilmadi" in not_found_login.json()["detail"]

        # 4b. Wrong password login -> specific "parol noto'g'ri" error
        bad_login = await client.post(
            "/api/auth/login",
            json={
                "username": "sardorbek",
                "password": "wrongpassword",
            },
        )
        assert bad_login.status_code == 401
        assert "parol noto'g'ri" in bad_login.json()["detail"].lower()

        # 5. Get current profile /api/auth/me
        me_resp = await client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token1}"},
        )
        assert me_resp.status_code == 200
        assert me_resp.json()["username"] == "sardorbek"

        # 6. User 1 creates a field
        field_payload = {
            "geometry": polygon_geojson,
            "crop_name": "Paxta",
            "planted_on": "2026-04-01",
            "growth_stage": "Gullash",
        }
        create_resp = await client.post(
            "/api/fields",
            json=field_payload,
            headers={"Authorization": f"Bearer {token1}"},
        )
        assert create_resp.status_code == 201

        # 7. User 1 lists fields
        list1 = await client.get(
            "/api/fields",
            headers={"Authorization": f"Bearer {token1}"},
        )
        assert list1.status_code == 200
        assert len(list1.json()) == 1
        assert list1.json()[0]["crop_name"] == "Paxta"

        # 8. Register User 2
        reg2 = await client.post(
            "/api/auth/register",
            json={
                "username": "nodirbek",
                "password": "password456",
                "full_name": "Nodirbek",
            },
        )
        assert reg2.status_code == 201
        token2 = reg2.json()["token"]

        # 9. User 2 lists fields -> should be empty (strict field isolation!)
        list2 = await client.get(
            "/api/fields",
            headers={"Authorization": f"Bearer {token2}"},
        )
        assert list2.status_code == 200
        assert len(list2.json()) == 0

        # 10. Logout User 1
        logout_resp = await client.post(
            "/api/auth/logout",
            headers={"Authorization": f"Bearer {token1}"},
        )
        assert logout_resp.status_code == 200

        # 11. After logout, session is invalidated in SQLite -> 401 Unauthorized
        me_after_logout = await client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token1}"},
        )
        assert me_after_logout.status_code == 401
