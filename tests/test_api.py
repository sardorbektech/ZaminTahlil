from pathlib import Path

import httpx
import pytest

from app.config import Settings
from app.db import Database
from app.main import app
from app.rendering import ArtifactWriter
from app.repository import Repository


@pytest.mark.asyncio
async def test_field_api_area_duplicate_and_missing_credentials(
    tmp_path: Path, polygon_geojson: dict[str, object]
) -> None:
    database = Database(tmp_path / "api.sqlite3")
    database.initialize()
    app.state.repository = Repository(database)
    app.state.artifact_writer = ArtifactWriter(tmp_path / "artifacts")
    app.state.settings = Settings(
        database_path=tmp_path / "api.sqlite3",
        artifact_dir=tmp_path / "artifacts",
        sentinel_hub_client_id=None,
        sentinel_hub_client_secret=None,
    )
    app.state.ai = None
    app.state.sentinel = None
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        health = await client.get("/api/health")
        assert health.status_code == 200 and health.json() == {"status": "ok"}
        payload = {
            "geometry": polygon_geojson,
            "crop_name": "Paxta",
            "planted_on": "2026-04-01",
            "growth_stage": "Gullash",
        }
        created = await client.post("/api/fields", json=payload)
        assert created.status_code == 201
        assert 90 < created.json()["area_hectares"] < 100
        duplicate = await client.post("/api/fields", json=payload)
        assert duplicate.status_code == 409
        analysis = await client.post("/api/fields/1/analyze", json={"mode": "latest"})
        assert analysis.status_code == 503
        assert "credentials" in analysis.json()["detail"]
        annual = await client.get("/api/fields/1/annual-metrics?year=2026")
        assert annual.status_code == 200
        assert annual.json()["indexes"] == ["NDVI", "NDMI", "NDRE", "EVI", "BSI"]
        assert annual.json()["points"] == []
        saved_history = await client.get("/api/fields/1/historical-metrics?from_date=2025-01-01")
        assert saved_history.status_code == 200
        assert saved_history.json()["points"] == []
        history = await client.post(
            "/api/fields/1/historical-metrics", json={"from_date": "2025-01-01"}
        )
        assert history.status_code == 503
        future = await client.post(
            "/api/fields/1/historical-metrics", json={"from_date": "2100-01-01"}
        )
        assert future.status_code == 422
