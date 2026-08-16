from datetime import date
from pathlib import Path

import pytest

from app.db import Database
from app.geometry import (
    canonical_geojson_and_hash,
    geodesic_area_hectares,
    validate_polygon_geojson,
)
from app.repository import Repository


@pytest.fixture
def polygon_geojson() -> dict[str, object]:
    return {
        "type": "Polygon",
        "coordinates": [
            [[69.20, 41.20], [69.21, 41.20], [69.21, 41.21], [69.20, 41.21], [69.20, 41.20]]
        ],
    }


@pytest.fixture
def repository(tmp_path: Path, polygon_geojson: dict[str, object]) -> Repository:
    database = Database(tmp_path / "test.sqlite3")
    database.initialize()
    repo = Repository(database)
    polygon = validate_polygon_geojson(polygon_geojson)
    canonical, geometry_hash = canonical_geojson_and_hash(polygon)
    repo.create_field(
        geometry=canonical,
        geometry_hash=geometry_hash,
        area_hectares=geodesic_area_hectares(polygon),
        crop_name="Paxta",
        planted_on=date(2026, 4, 1),
        growth_stage="Gullash",
    )
    return repo
