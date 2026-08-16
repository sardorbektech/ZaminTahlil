import logging
from pathlib import Path

import httpx
import pytest

from app.config import Settings
from app.security import SensitiveDataFilter


def _prod_settings(tmp_path: Path) -> Settings:
    return Settings(
        app_env="prod",
        cors_origins="https://example.uz",
        database_path=tmp_path / "s.sqlite3",
        artifact_dir=tmp_path / "art",
    )


def _demo_settings(tmp_path: Path) -> Settings:
    return Settings(
        database_path=tmp_path / "d.sqlite3",
        artifact_dir=tmp_path / "dart",
    )


@pytest.mark.asyncio
async def test_prod_disables_docs(tmp_path: Path) -> None:
    from app.main import create_app

    app = create_app(_prod_settings(tmp_path))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        for path in ("/docs", "/redoc", "/openapi.json"):
            resp = await client.get(path)
            assert resp.status_code == 404, f"{path} should be disabled in prod"


@pytest.mark.asyncio
async def test_security_headers_and_hsts(tmp_path: Path) -> None:
    from app.main import create_app

    app = create_app(_prod_settings(tmp_path))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/health")
        assert resp.status_code == 200
        assert resp.headers["x-content-type-options"] == "nosniff"
        assert resp.headers["x-frame-options"] == "DENY"
        assert resp.headers["referrer-policy"] == "strict-origin-when-cross-origin"
        assert "permissions-policy" in resp.headers
        # Plain http: HSTS yo'q
        assert "strict-transport-security" not in resp.headers

        # x-forwarded-proto: https -> HSTS bor
        resp_https = await client.get(
            "/api/health", headers={"x-forwarded-proto": "https"}
        )
        assert resp_https.status_code == 200
        assert "strict-transport-security" in resp_https.headers


@pytest.mark.asyncio
async def test_cors_prod_restricted(tmp_path: Path) -> None:
    from app.main import create_app

    app = create_app(_prod_settings(tmp_path))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Yopiq kelib chiqishi: CORS sarlavhasi yo'q
        evil = await client.get("/api/health", headers={"Origin": "https://evil.com"})
        assert "access-control-allow-origin" not in evil.headers

        # Ruxsat etilgan kelib chiqish: aniq origin qaytadi, * emas
        allowed = await client.get("/api/health", headers={"Origin": "https://example.uz"})
        assert allowed.headers.get("access-control-allow-origin") == "https://example.uz"


@pytest.mark.asyncio
async def test_demo_keeps_docs_and_wildcard_cors(tmp_path: Path) -> None:
    from app.main import create_app

    app = create_app(_demo_settings(tmp_path))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        docs = await client.get("/docs")
        assert docs.status_code == 200
        health = await client.get("/api/health", headers={"Origin": "http://localhost:5173"})
        # Demo rejimida har qanday origin ruxsat etiladi; allow_credentials=True
        # bo'lgani uchun Starlette originni aks ettiradi (`*` o'rniga).
        acao = health.headers.get("access-control-allow-origin")
        assert acao in ("*", "http://localhost:5173")


@pytest.mark.asyncio
async def test_prod_catch_all_hides_secrets(tmp_path: Path) -> None:
    from app.main import create_app

    app = create_app(_prod_settings(tmp_path))

    @app.get("/api/boom")
    async def _boom() -> None:
        raise RuntimeError("secret trace sk-abcdef123456")

    # StaticFiles mount `/` route'dan keyin qo'shilgan, shuning uchun boom
    # route'ni ro'yxat boshiga ko'chiramiz (mountdan oldin tekshirilishi uchun).
    boom_route = app.router.routes.pop()
    app.router.routes.insert(0, boom_route)

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/boom")
        assert resp.status_code == 500
        assert resp.json() == {"detail": "Ichki server xatosi"}
        body = resp.text
        assert "secret" not in body
        assert "sk-" not in body


def test_sensitive_data_filter_masks_tokens_and_keys() -> None:
    filt = SensitiveDataFilter()
    record = logging.makeLogRecord(
        {"msg": "token sk-abcdef123456 Bearer xyz789 client_secret=topsecret value"}
    )
    assert filt.filter(record) is True
    masked = record.getMessage()
    assert "***" in masked
    assert "sk-abcdef123456" not in masked
    assert "xyz789" not in masked
    assert "topsecret" not in masked


def test_sensitive_data_filter_extra_literal_secret() -> None:
    filt = SensitiveDataFilter(["my-literal-secret"])
    record = logging.makeLogRecord({"msg": "config my-literal-secret loaded"})
    assert filt.filter(record) is True
    masked = record.getMessage()
    assert "my-literal-secret" not in masked
    assert "***" in masked
