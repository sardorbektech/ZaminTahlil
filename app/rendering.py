import hashlib
import os
import re
import tempfile
from pathlib import Path

import numpy as np
import numpy.typing as npt
from PIL import Image

from app.constants import RENDER_VERSION
from app.sentinel import RasterData


def render_rgb(raster: RasterData) -> npt.NDArray[np.uint8]:
    rgb = np.stack([raster.bands["B04"], raster.bands["B03"], raster.bands["B02"]], axis=-1)
    normalized = np.clip(rgb, 0.0, 0.30) / 0.30
    corrected = np.power(normalized, 1 / 2.2)
    alpha = (raster.data_mask.astype(np.uint8) * 255)[..., np.newaxis]
    return np.concatenate([(corrected * 255).round().astype(np.uint8), alpha], axis=-1)


def render_heatmap(
    values: npt.NDArray[np.float32], valid: npt.NDArray[np.bool_]
) -> npt.NDArray[np.uint8]:
    brown = np.array([140, 81, 10], dtype=np.float32)
    neutral = np.array([246, 232, 195], dtype=np.float32)
    teal = np.array([1, 102, 94], dtype=np.float32)
    clipped = np.nan_to_num(np.clip(values, -1, 1), nan=0.0)
    negative_weight = np.clip(clipped + 1, 0, 1)[..., np.newaxis]
    positive_weight = np.clip(clipped, 0, 1)[..., np.newaxis]
    negative_colors = brown * (1 - negative_weight) + neutral * negative_weight
    positive_colors = neutral * (1 - positive_weight) + teal * positive_weight
    colors = np.where((clipped <= 0)[..., np.newaxis], negative_colors, positive_colors)
    alpha = (valid.astype(np.uint8) * 255)[..., np.newaxis]
    return np.concatenate([colors.round().astype(np.uint8), alpha], axis=-1)


def render_qa(raster: RasterData) -> npt.NDArray[np.uint8]:
    rgba = np.zeros((*raster.scl.shape, 4), dtype=np.uint8)
    cloud_shadow = raster.data_mask & (raster.scl == 3)
    cloud = raster.data_mask & np.isin(raster.scl, [8, 9, 10])
    invalid = raster.data_mask & np.isin(raster.scl, [0, 1, 11])
    rgba[cloud_shadow] = [70, 70, 70, 210]
    rgba[cloud] = [170, 170, 170, 220]
    rgba[invalid] = [90, 90, 110, 190]
    return rgba


def _safe_segment(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]", "_", value)[:48]
    digest = hashlib.sha256(value.encode()).hexdigest()[:10]
    return f"{cleaned}-{digest}"


class ArtifactWriter:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def relative_path(
        self, field_id: int, product_id: str, revision_key: str, layer_name: str
    ) -> Path:
        return Path(
            f"field-{field_id}",
            _safe_segment(product_id),
            _safe_segment(revision_key),
            RENDER_VERSION,
            f"{layer_name}.png",
        )

    def write_atomic(self, relative_path: Path, rgba: npt.NDArray[np.uint8]) -> None:
        target = (self.root / relative_path).resolve()
        if not target.is_relative_to(self.root):
            raise ValueError("Artifact yo'li katalogdan tashqariga chiqdi")
        target.parent.mkdir(parents=True, exist_ok=True)
        file_descriptor, temporary_name = tempfile.mkstemp(dir=target.parent, suffix=".png.tmp")
        try:
            os.close(file_descriptor)
            Image.fromarray(rgba, mode="RGBA").save(temporary_name, format="PNG")
            os.replace(temporary_name, target)
        finally:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)

    def values_relative_path(
        self, field_id: int, product_id: str, revision_key: str, index_name: str
    ) -> Path:
        return Path(
            f"field-{field_id}",
            _safe_segment(product_id),
            _safe_segment(revision_key),
            RENDER_VERSION,
            "values",
            f"{index_name}.npy",
        )

    def write_values_atomic(self, relative_path: Path, values: npt.NDArray[np.float32]) -> None:
        target = (self.root / relative_path).resolve()
        if not target.is_relative_to(self.root):
            raise ValueError("Metrika yo'li katalogdan tashqariga chiqdi")
        target.parent.mkdir(parents=True, exist_ok=True)
        file_descriptor, temporary_name = tempfile.mkstemp(dir=target.parent, suffix=".npy.tmp")
        try:
            with os.fdopen(file_descriptor, "wb") as stream:
                np.save(stream, values.astype(np.float32, copy=False), allow_pickle=False)
            os.replace(temporary_name, target)
        finally:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)

    def read_values(self, relative_path: str) -> npt.NDArray[np.float32]:
        path = self._resolve(relative_path)
        if not path.is_file():
            raise FileNotFoundError("Metrika qiymatlari topilmadi")
        values = np.load(path, allow_pickle=False)
        return np.asarray(values, dtype=np.float32)

    def delete_relative(self, relative_path: str) -> None:
        path = self._resolve(relative_path)
        if path.is_file():
            path.unlink()

    def _resolve(self, relative_path: str) -> Path:
        candidate = (self.root / relative_path).resolve()
        if not candidate.is_relative_to(self.root):
            raise FileNotFoundError("Artifact fayli topilmadi")
        return candidate

    def resolve_existing(self, relative_path: str) -> Path:
        candidate = self._resolve(relative_path)
        if not candidate.is_file():
            raise FileNotFoundError("Artifact fayli topilmadi")
        return candidate
