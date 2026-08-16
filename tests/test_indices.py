import numpy as np

from app.constants import INDEX_NAMES
from app.indices import calculate_indices, calculate_stats


def bands(**overrides: float) -> dict[str, np.ndarray]:
    defaults = {
        "B02": 0.1,
        "B03": 0.2,
        "B04": 0.3,
        "B05": 0.35,
        "B08": 0.6,
        "B8A": 0.58,
        "B11": 0.4,
        "B12": 0.25,
    }
    defaults.update(overrides)
    return {name: np.full((2, 2), value, dtype=np.float32) for name, value in defaults.items()}


def test_only_five_approved_indexes_are_calculated() -> None:
    result = calculate_indices(bands(), np.ones((2, 2), dtype=bool))
    assert tuple(result) == INDEX_NAMES
    assert np.allclose(result["NDMI"], (0.6 - 0.4) / (0.6 + 0.4))
    assert set(result) == {"NDVI", "NDMI", "NDRE", "EVI", "BSI"}


def test_zero_denominator_invalid_mask_and_clamp() -> None:
    invalid = calculate_indices(bands(B08=0, B04=0), np.ones((2, 2), dtype=bool))["NDVI"]
    assert np.isnan(invalid).all()
    masked = calculate_indices(bands(), np.zeros((2, 2), dtype=bool))["NDVI"]
    assert np.isnan(masked).all()
    extreme = calculate_indices(bands(B08=100, B04=-99), np.ones((2, 2), dtype=bool))["NDVI"]
    assert np.nanmax(extreme) == 1


def test_min_mean_median_max_and_empty_statistics() -> None:
    values = np.array([[-2, -0.5], [0.5, 2]], dtype=np.float32)
    stats = calculate_stats(values)
    assert (stats.minimum, stats.mean, stats.median, stats.maximum, stats.valid_pixel_count) == (
        -1,
        0,
        0,
        1,
        4,
    )
    empty = calculate_stats(np.full((2, 2), np.nan, dtype=np.float32))
    assert empty.minimum is empty.mean is empty.median is empty.maximum is None
    assert empty.valid_pixel_count == 0
