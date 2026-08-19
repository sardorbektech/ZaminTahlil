import numpy as np
import pytest

from app.anomaly import (
    compute_biophysical_indices,
    compute_furrow_anisotropy,
    compute_metrics_distribution,
    detect_and_cluster_anomalies,
    determine_compass_sector,
    evaluate_differential_diagnosis,
)


def test_compute_biophysical_indices_ranges():
    h, w = 20, 20
    valid = np.ones((h, w), dtype=bool)
    bands = {
        "B02": np.full((h, w), 0.05, dtype=np.float32),
        "B03": np.full((h, w), 0.08, dtype=np.float32),
        "B04": np.full((h, w), 0.06, dtype=np.float32),
        "B05": np.full((h, w), 0.12, dtype=np.float32),
        "B08": np.full((h, w), 0.45, dtype=np.float32),
        "B8A": np.full((h, w), 0.44, dtype=np.float32),
        "B11": np.full((h, w), 0.15, dtype=np.float32),
    }

    indices = compute_biophysical_indices(bands, valid)
    required_indices = [
        "NDVI",
        "SAVI",
        "EVI",
        "LAI",
        "NDRE",
        "BRI",
        "LCI",
        "NDWI",
        "NDMI",
        "MSI",
        "NDSI",
        "BSI",
        "Delta_T",
    ]
    for name in required_indices:
        assert name in indices
        assert indices[name].shape == (h, w)
        assert np.all(np.isfinite(indices[name]))

    # NDVI = (0.45 - 0.06) / (0.45 + 0.06) = 0.39 / 0.51 ~= 0.7647
    assert 0.75 < float(np.mean(indices["NDVI"])) < 0.78
    # NDWI = (0.44 - 0.15) / (0.44 + 0.15) = 0.29 / 0.59 ~= 0.4915
    assert 0.48 < float(np.mean(indices["NDWI"])) < 0.51
    # Delta T for healthy vegetation should be low (~0 C)
    assert float(np.mean(indices["Delta_T"])) < 1.0


def test_compass_sector_directions():
    center_r, center_c = 50.0, 50.0

    assert determine_compass_sector(50.0, 50.0, center_r, center_c) == "Markaziy"
    # Yuqorida (Shimoliy: row < center_r)
    assert determine_compass_sector(10.0, 50.0, center_r, center_c) == "Shimoliy"
    # Pastda (Janubiy: row > center_r)
    assert determine_compass_sector(90.0, 50.0, center_r, center_c) == "Janubiy"
    # O'ngda (Sharqiy: col > center_c)
    assert determine_compass_sector(50.0, 90.0, center_r, center_c) == "Sharqiy"
    # Chapda (G'arbiy: col < center_c)
    assert determine_compass_sector(50.0, 10.0, center_r, center_c) == "G'arbiy"
    # Shimoli-sharqiy (row < 50, col > 50)
    assert determine_compass_sector(20.0, 80.0, center_r, center_c) == "Shimoli-sharqiy"
    # Janubi-g'arbiy (row > 50, col < 50)
    assert determine_compass_sector(80.0, 20.0, center_r, center_c) == "Janubi-g'arbiy"


def test_furrow_anisotropy_e_index():
    # Linear furrow-aligned elongation: points along a line
    rows_linear = np.array([10, 15, 20, 25, 30, 35, 40, 45])
    cols_linear = np.array([10, 10, 11, 10, 11, 10, 10, 11])  # Straight vertical furrow
    e_val, o_type, o_label = compute_furrow_anisotropy(rows_linear, cols_linear)
    assert e_val > 3.0
    assert o_type == "linear_furrow"

    # Symmetric concentric circle
    angles = np.linspace(0, 2 * np.pi, 16)
    rows_circle = np.round(20 + 5 * np.sin(angles)).astype(int)
    cols_circle = np.round(20 + 5 * np.cos(angles)).astype(int)
    e_circle, o_type_c, _ = compute_furrow_anisotropy(rows_circle, cols_circle)
    assert e_circle <= 3.0
    assert o_type_c == "concentric_radial"


def test_differential_decision_tree():
    # 1. Osmotic Salinity: NDSI >= 0.38, SAVI < 0.30
    means_salinity = {"NDSI": 0.42, "SAVI": 0.22, "NDRE": 0.30, "BRI": 1.1, "NDWI": 0.20, "NDVI": 0.25}
    risk, title, code, pathogen, treatment, action = evaluate_differential_diagnosis(
        means_salinity, historical_ndre_before_ndwi_drop=False, crop_name="Paxta"
    )
    assert risk == "CRITICAL"
    assert "Sho'rlanish" in title
    assert code == "SALINITY_OSMOTIC_STRESS"
    assert "sho'r yuvish" in treatment.lower()

    # 2. Early Fungal: NDRE < 0.45, BRI > 1.20, NDWI >= 0.38
    means_fungal = {"NDSI": 0.10, "SAVI": 0.40, "NDRE": 0.35, "BRI": 1.35, "NDWI": 0.42, "NDVI": 0.48}
    risk, title, code, pathogen, treatment, action = evaluate_differential_diagnosis(
        means_fungal, historical_ndre_before_ndwi_drop=False, crop_name="Paxta"
    )
    assert risk == "HIGH"
    assert "Zamburug'li" in title
    assert pathogen is not None and "Verticillium" in pathogen
    assert "Topsin-M" in treatment

    # 3. Late Pathogen vs Pure Hydro Stress: NDWI < 0.25, NDRE < 0.40
    means_water_stress = {"NDSI": 0.10, "SAVI": 0.35, "NDRE": 0.32, "BRI": 1.0, "NDWI": 0.18, "NDVI": 0.35}
    # Case A: NDRE dropped before NDWI -> Late Pathogen Xylem Blockade
    risk_a, title_a, code_a, pathogen_a, _, _ = evaluate_differential_diagnosis(
        means_water_stress, historical_ndre_before_ndwi_drop=True, crop_name="Paxta"
    )
    assert risk_a == "CRITICAL"
    assert "Ksilema" in title_a
    assert pathogen_a is not None and "Verticillium" in pathogen_a

    # Case B: NDWI dropped before NDRE -> Pure Hydro Stress
    risk_b, title_b, code_b, pathogen_b, treatment_b, _ = evaluate_differential_diagnosis(
        means_water_stress, historical_ndre_before_ndwi_drop=False, crop_name="Paxta"
    )
    assert risk_b == "HIGH"
    assert "Gidro-Stress" in title_b
    assert pathogen_b is None
    assert "sug'orish" in treatment_b.lower()


def test_detect_and_cluster_anomalies_full_pipeline():
    h, w = 60, 60
    valid = np.ones((h, w), dtype=bool)
    bands = {
        "B02": np.full((h, w), 0.05, dtype=np.float32),
        "B03": np.full((h, w), 0.08, dtype=np.float32),
        "B04": np.full((h, w), 0.06, dtype=np.float32),
        "B05": np.full((h, w), 0.12, dtype=np.float32),
        "B08": np.full((h, w), 0.50, dtype=np.float32),
        "B8A": np.full((h, w), 0.48, dtype=np.float32),
        "B11": np.full((h, w), 0.15, dtype=np.float32),
    }

    # Create artificial Hotspot 1: Salinity stress in South-East (rows 45:55, cols 45:55)
    bands["B03"][45:55, 45:55] = 0.30
    bands["B11"][45:55, 45:55] = 0.05  # High NDSI
    bands["B08"][45:55, 45:55] = 0.10
    bands["B04"][45:55, 45:55] = 0.20  # Low NDVI/SAVI

    # Create artificial Hotspot 2: Single noise pixel (should be filtered)
    bands["B08"][5, 5] = 0.05

    report = detect_and_cluster_anomalies(bands, valid, crop_name="Paxta")
    assert report.cluster_count >= 1
    assert len(report.top_clusters) >= 1
    top = report.top_clusters[0]

    assert top.compass_sector == "Janubi-sharqiy"
    assert top.risk_level == "CRITICAL"
    assert "Sho'rlanish" in top.diagnosis_title
    assert report.anomaly_percentage > 0.0
    assert "NDVI" in report.field_metrics_summary
    assert "min" in report.field_metrics_summary["NDVI"]
    assert "mean" in report.field_metrics_summary["NDVI"]
    assert "median" in report.field_metrics_summary["NDVI"]
    assert "max" in report.field_metrics_summary["NDVI"]
