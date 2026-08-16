from pathlib import Path

import numpy as np
import pytest

from app.rendering import ArtifactWriter, render_heatmap, render_qa, render_rgb
from app.sentinel import RasterData, valid_pixel_mask


def raster(scl_value: int = 4) -> RasterData:
    band_values = {
        name: np.full((2, 3), 0.15, dtype=np.float32)
        for name in ("B02", "B03", "B04", "B05", "B08", "B8A", "B11", "B12")
    }
    band_values["B04"][:] = 0.30
    band_values["B03"][:] = 0.15
    band_values["B02"][:] = 0
    return RasterData(
        band_values,
        np.full((2, 3), scl_value, dtype=np.uint8),
        np.ones((2, 3), dtype=bool),
        [69, 41, 70, 42],
        3,
        2,
    )


def test_rgb_channel_order_fixed_range_gamma_and_grid() -> None:
    image = render_rgb(raster())
    expected_green = round(((0.15 / 0.30) ** (1 / 2.2)) * 255)
    assert image.shape == (2, 3, 4)
    assert tuple(image[0, 0]) == (255, expected_green, 0, 255)


def test_cloud_heatmap_is_transparent_and_qa_is_gray() -> None:
    value = raster(9)
    valid = valid_pixel_mask(value)
    heatmap = render_heatmap(np.zeros((2, 3), dtype=np.float32), valid)
    qa = render_qa(value)
    assert not valid.any()
    assert not heatmap[..., 3].any()
    assert np.all(qa[..., 3] > 0)


def test_artifact_path_is_scoped_and_traversal_blocked(tmp_path: Path) -> None:
    writer = ArtifactWriter(tmp_path / "artifacts")
    relative = writer.relative_path(1, "product/../unsafe", "rev", "NDVI")
    writer.write_atomic(relative, np.zeros((1, 1, 4), dtype=np.uint8))
    assert writer.resolve_existing(relative.as_posix()).is_file()
    with pytest.raises(FileNotFoundError):
        writer.resolve_existing("../../outside.png")
