from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from app.constants import INDEX_NAMES

FloatArray = npt.NDArray[np.float32]
BoolArray = npt.NDArray[np.bool_]


@dataclass(frozen=True)
class IndexStats:
    minimum: float | None
    mean: float | None
    median: float | None
    maximum: float | None
    valid_pixel_count: int


def _ratio(numerator: FloatArray, denominator: FloatArray, valid: BoolArray) -> FloatArray:
    result = np.full(numerator.shape, np.nan, dtype=np.float32)
    safe = valid & np.isfinite(numerator) & np.isfinite(denominator) & (denominator != 0)
    np.divide(numerator, denominator, out=result, where=safe)
    return np.clip(result, -1.0, 1.0).astype(np.float32)


def calculate_indices(bands: Mapping[str, FloatArray], valid: BoolArray) -> dict[str, FloatArray]:
    b2, b4, b5 = bands["B02"], bands["B04"], bands["B05"]
    b8, b8a, b11 = bands["B08"], bands["B8A"], bands["B11"]
    raw: dict[str, FloatArray] = {
        "NDVI": _ratio(b8 - b4, b8 + b4, valid),
        "NDMI": _ratio(b8 - b11, b8 + b11, valid),
        "NDRE": _ratio(b8a - b5, b8a + b5, valid),
        "EVI": _ratio(2.5 * (b8 - b4), b8 + 6 * b4 - 7.5 * b2 + 1, valid),
        "BSI": _ratio((b11 + b4) - (b8 + b2), (b11 + b4) + (b8 + b2), valid),
    }
    return {name: raw[name] for name in INDEX_NAMES}


def calculate_stats(values: FloatArray) -> IndexStats:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return IndexStats(None, None, None, None, 0)
    clipped = np.clip(finite, -1, 1)
    return IndexStats(
        minimum=float(np.min(clipped)),
        mean=float(np.mean(clipped)),
        median=float(np.median(clipped)),
        maximum=float(np.max(clipped)),
        valid_pixel_count=int(clipped.size),
    )
