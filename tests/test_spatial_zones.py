from pathlib import Path
import numpy as np
import pytest
from starlette.testclient import TestClient

from app.main import create_app
from app.spatial_zones import (
    calculate_spatial_problem_zones,
    sector_to_human_phrase,
    _find_lowest_stress_centroid,
)


def test_sector_to_human_phrase() -> None:
    assert "yuqori o'ng" in sector_to_human_phrase("Shimoli-sharqiy")
    assert "yuqori chap" in sector_to_human_phrase("Shimoli-g'arbiy")
    assert "pastki o'ng" in sector_to_human_phrase("Janubi-sharqiy")
    assert "pastki chap" in sector_to_human_phrase("Janubi-g'arbiy")
    assert "markaziy" in sector_to_human_phrase("Markaziy")


def test_find_lowest_stress_centroid() -> None:
    # 10x10 array, normal values 0.5, with a dry spot at top-right (row 1, col 8)
    arr = np.full((10, 10), 0.5, dtype=np.float32)
    arr[0:2, 8:10] = 0.05  # lowest values in top-right

    centroid = _find_lowest_stress_centroid(arr, percentile=10.0)
    assert centroid is not None
    c_row, c_col, mean_val = centroid
    assert 0.0 <= c_row <= 1.0
    assert 8.0 <= c_col <= 9.0
    assert mean_val < 0.10


def test_spatial_problem_zones_with_rasters(tmp_path: Path) -> None:
    # Configure app with tmp database and artifacts
    db_path = tmp_path / "test.db"
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    from app.config import Settings
    settings = Settings(
        database_path=db_path,
        artifact_dir=artifacts_dir,
        app_env="demo",
    )
    app = create_app(settings)
    client = TestClient(app)

    # 1. Register field
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
    field_resp = client.post(
        "/api/fields",
        json={
            "geometry": polygon,
            "crop_name": "Bug'doy",
            "planted_on": "2026-03-01",
            "growth_stage": "Naychalash",
        },
    )
    assert field_resp.status_code == 201
    field_id = field_resp.json()["id"]

    # 2. Before any acquisitions
    res_empty = calculate_spatial_problem_zones(
        field_id,
        app.state.repository,
        artifact_root=artifacts_dir,
    )
    assert res_empty["has_data"] is False

    # 3. Add acquisition & write raster .npy files
    rel_ndmi = f"field-{field_id}/test/values/NDMI.npy"
    rel_ndre = f"field-{field_id}/test/values/NDRE.npy"
    p_ndmi = artifacts_dir / rel_ndmi
    p_ndre = artifacts_dir / rel_ndre
    p_ndmi.parent.mkdir(parents=True, exist_ok=True)

    # NDMI: dry spot at top-right (row 0..2, col 8..10)
    ndmi_data = np.full((10, 10), 0.40, dtype=np.float32)
    ndmi_data[0:2, 8:10] = 0.05
    np.save(p_ndmi, ndmi_data)

    # NDRE: chlorosis spot at bottom-left (row 8..10, col 0..2)
    ndre_data = np.full((10, 10), 0.60, dtype=np.float32)
    ndre_data[8:10, 0:2] = 0.15
    np.save(p_ndre, ndre_data)

    with app.state.repository.database.connect() as conn:
        cur = conn.execute(
            """INSERT INTO acquisitions(field_id, acquired_at, product_id, revision_key, source_metadata_json, created_at)
            VALUES (?, datetime('now'), 'S2_TEST_SPATIAL', 'rev1', '{}', datetime('now'))""",
            (field_id,),
        )
        acq_id = int(cur.lastrowid or 0)
        conn.execute(
            """INSERT INTO index_values(acquisition_id, index_name, relative_path, valid_pixel_count, mean_value, min_value, median_value, max_value)
            VALUES (?, 'NDMI', ?, 100, 0.35, 0.05, 0.40, 0.40),
                   (?, 'NDRE', ?, 100, 0.55, 0.15, 0.60, 0.60)""",
            (acq_id, rel_ndmi, acq_id, rel_ndre),
        )

    # Calculate zones
    zones = calculate_spatial_problem_zones(
        field_id,
        app.state.repository,
        artifact_root=artifacts_dir,
    )
    assert zones["has_data"] is True
    assert zones["water_stress"] is not None
    assert "yuqori o'ng" in zones["water_stress"]["human_location"]
    assert zones["disease_stress"] is not None
    assert "pastki chap" in zones["disease_stress"]["human_location"]
    assert "Suvsizlik" in zones["summary_uz"]

    # Test REST endpoint
    ep_resp = client.get(f"/api/fields/{field_id}/problem-zones")
    assert ep_resp.status_code == 200
    ep_data = ep_resp.json()
    assert ep_data["has_data"] is True
    assert "water_stress" in ep_data
    assert "disease_stress" in ep_data
