from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.yield_service import (
    YieldInferenceService,
    build_monthly_ml_features,
    generate_phenology_timeline,
    normalize_crop_name,
    process_raw_observations,
)


def test_normalize_crop_name() -> None:
    assert normalize_crop_name("Paxta") == "cotton"
    assert normalize_crop_name("G'o'za") == "cotton"
    assert normalize_crop_name("Bug'doy") == "wheat"
    assert normalize_crop_name("Kuzgi bug‘doy") == "wheat"
    assert normalize_crop_name("Boshqa ekin") == "cotton"


def test_yield_feature_engineering_and_inference() -> None:
    dates = pd.date_range("2026-04-01", "2026-10-31", freq="10D")
    df_s2 = pd.DataFrame(
        {
            "date": dates,
            "s2_b02_blue": 0.04,
            "s2_b03_green": 0.07,
            "s2_b04_red": 0.05,
            "s2_b05_red_edge_1": 0.12,
            "s2_b06_red_edge_2": 0.22,
            "s2_b07_red_edge_3": 0.28,
            "s2_b08_nir": 0.38,
            "s2_b8a_nir_narrow": 0.40,
            "s2_b11_swir_1": 0.17,
            "s2_b12_swir_2": 0.09,
            "s2_cloud_percentage": 5.0,
            "s2_cloud_probability": 4.0,
        }
    )
    df_s1 = pd.DataFrame({"date": dates, "s1_vv": -11.0, "s1_vh": -16.0})
    df_w = pd.DataFrame(
        {
            "date": dates,
            "weather_temperature_2m": 25.0,
            "weather_apparent_temperature": 24.5,
            "weather_total_precipitation": 1.0,
            "weather_rain": 1.0,
            "weather_shortwave_radiation": 20.0,
            "weather_wind_speed_10m": 10.0,
            "weather_soil_temperature_0_7cm": 23.0,
            "weather_soil_moisture_0_7cm": 0.25,
            "weather_soil_moisture_7_28cm": 0.27,
            "weather_soil_moisture_28_100cm": 0.30,
            "weather_evapotranspiration_et0": 4.0,
            "latitude": 40.5,
            "longitude": 68.5,
        }
    )

    s2_proc, s1_proc, w_proc = process_raw_observations(
        df_s2, df_s1, df_w, planting_date="2026-04-15", harvest_date="2026-10-15"
    )
    assert "s2_ndvi" in s2_proc.columns
    assert "s2_evi" in s2_proc.columns
    assert "s1_vv_vh_ratio" in s1_proc.columns
    assert "crop_age_days" in w_proc.columns

    df_feats = build_monthly_ml_features(s2_proc, s1_proc, w_proc, target_year=2026)
    assert not df_feats.empty
    assert "month_sin" in df_feats.columns

    service = YieldInferenceService(models_dir=Path("models"))
    models = service.list_available_models()
    assert len(models) > 0

    # Cotton inference
    yield_val, y_min, y_max, top_feats, model_name = service.predict_yield(
        df_features=df_feats, crop="cotton", model_name="CatBoost"
    )
    assert yield_val > 0.0
    assert y_min <= yield_val <= y_max
    assert len(top_feats) > 0

    timeline = generate_phenology_timeline(s2_proc, s1_proc, w_proc)
    assert len(timeline) > 0


def test_yield_api_endpoints(tmp_path: Path) -> None:
    settings = Settings(
        app_env="demo",
        database_path=tmp_path / "test.db",
        artifact_dir=tmp_path / "artifacts",
        models_dir=Path("models"),
    )
    app = create_app(settings)
    with TestClient(app) as client:
        # 1. Models list
        resp = client.get("/api/yield/models")
        assert resp.status_code == 200
        data = resp.json()
        assert "models" in data
        assert "calendars" in data

        # 2. Create field
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
        assert field_resp.status_code == 201
        field_id = field_resp.json()["id"]

        # 3. Predict yield
        pred_resp = client.post(
            f"/api/fields/{field_id}/predict-yield",
            json={"model_name": "CatBoost", "crop": "cotton"},
        )
        assert pred_resp.status_code == 200
        pred_data = pred_resp.json()
        assert pred_data["crop"] == "cotton"
        assert pred_data["predicted_yield_t_ha"] > 0
        assert pred_data["total_expected_yield_tons"] > 0
        assert len(pred_data["top_features"]) > 0

        # 4. Get latest yield
        latest_resp = client.get(f"/api/fields/{field_id}/yield-latest")
        assert latest_resp.status_code == 200
        assert latest_resp.json() is not None
        assert latest_resp.json()["crop"] == "cotton"
