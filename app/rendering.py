import base64
import hashlib
import io
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
    values: npt.NDArray[np.float32],
    valid: npt.NDArray[np.bool_],
    layer_name: str = "NDVI",
) -> npt.NDArray[np.uint8]:
    """
    Maxsus dinamik ko'p bosqichli RGBA Color Mapping:
    - NDVI, NDRE, EVI, SAVI: [0.0 - 0.4] Qizil -> Sariq, [0.4 - 0.7] Sariq -> Och Yashil, [0.7 - 0.85+] Och Yashil -> To'q Zumrad Yashil.
    - NDMI, NDWI: Suv va barg namligi (Quruq -> Moviy -> To'q Ko'k).
    - BSI, NDSI: Sho'rlanish va ochiq tuproq (Yashil -> Sariq -> To'q Qizil).
    Dala tashqarisidagi piksellar: Alpha = 0 (100% shaffof).
    """
    h, w = values.shape
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    clean_vals = np.nan_to_num(values, nan=0.0)

    if layer_name in ("NDVI", "NDRE", "EVI", "SAVI"):
        norm = np.clip((clean_vals - 0.0) / 0.85, 0.0, 1.0)
        t1 = np.clip(norm / 0.4, 0.0, 1.0)
        r1 = (239 + (234 - 239) * t1).astype(np.uint8)
        g1 = (68 + (179 - 68) * t1).astype(np.uint8)
        b1 = (68 + (8 - 68) * t1).astype(np.uint8)

        t2 = np.clip((norm - 0.4) / 0.3, 0.0, 1.0)
        r2 = (234 + (34 - 234) * t2).astype(np.uint8)
        g2 = (179 + (197 - 179) * t2).astype(np.uint8)
        b2 = (8 + (94 - 8) * t2).astype(np.uint8)

        t3 = np.clip((norm - 0.7) / 0.3, 0.0, 1.0)
        r3 = (34 + (21 - 34) * t3).astype(np.uint8)
        g3 = (197 + (128 - 197) * t3).astype(np.uint8)
        b3 = (94 + (61 - 94) * t3).astype(np.uint8)

        r = np.where(norm < 0.4, r1, np.where(norm < 0.7, r2, r3))
        g = np.where(norm < 0.4, g1, np.where(norm < 0.7, g2, g3))
        b = np.where(norm < 0.4, b1, np.where(norm < 0.7, b2, b3))

        rgba[..., 0] = r
        rgba[..., 1] = g
        rgba[..., 2] = b
        rgba[..., 3] = np.where(valid, 220, 0).astype(np.uint8)

    elif layer_name in ("NDMI", "NDWI"):
        norm = np.clip((clean_vals + 0.2) / 0.8, 0.0, 1.0)
        t1 = np.clip(norm / 0.5, 0.0, 1.0)
        t2 = np.clip((norm - 0.5) / 0.5, 0.0, 1.0)
        r = np.where(norm < 0.5, 217 + (6 - 217) * t1, 6 + (29 - 6) * t2).astype(np.uint8)
        g = np.where(norm < 0.5, 119 + (182 - 119) * t1, 182 + (78 - 182) * t2).astype(np.uint8)
        b = np.where(norm < 0.5, 6 + (212 - 6) * t1, 212 + (216 - 212) * t2).astype(np.uint8)
        rgba[..., 0] = r
        rgba[..., 1] = g
        rgba[..., 2] = b
        rgba[..., 3] = np.where(valid, 220, 0).astype(np.uint8)

    elif layer_name in ("BSI", "NDSI"):
        norm = np.clip((clean_vals + 0.3) / 0.8, 0.0, 1.0)
        t1 = np.clip(norm / 0.5, 0.0, 1.0)
        t2 = np.clip((norm - 0.5) / 0.5, 0.0, 1.0)
        r = np.where(norm < 0.5, 34 + (245 - 34) * t1, 245 + (220 - 245) * t2).astype(np.uint8)
        g = np.where(norm < 0.5, 197 + (158 - 197) * t1, 158 + (38 - 158) * t2).astype(np.uint8)
        b = np.where(norm < 0.5, 94 + (11 - 94) * t1, 11 + (38 - 11) * t2).astype(np.uint8)
        rgba[..., 0] = r
        rgba[..., 1] = g
        rgba[..., 2] = b
        rgba[..., 3] = np.where(valid, 220, 0).astype(np.uint8)

    else:
        norm = np.clip((clean_vals + 1.0) / 2.0, 0.0, 1.0)
        rgba[..., 0] = (239 * (1 - norm) + 21 * norm).astype(np.uint8)
        rgba[..., 1] = (68 * (1 - norm) + 128 * norm).astype(np.uint8)
        rgba[..., 2] = (68 * (1 - norm) + 61 * norm).astype(np.uint8)
        rgba[..., 3] = np.where(valid, 220, 0).astype(np.uint8)

    return rgba


def render_qa(raster: RasterData) -> npt.NDArray[np.uint8]:
    rgba = np.zeros((*raster.scl.shape, 4), dtype=np.uint8)
    cloud_shadow = raster.data_mask & (raster.scl == 3)
    cloud = raster.data_mask & np.isin(raster.scl, [8, 9, 10])
    invalid = raster.data_mask & np.isin(raster.scl, [0, 1, 11])
    rgba[cloud_shadow] = [70, 70, 70, 210]
    rgba[cloud] = [170, 170, 170, 220]
    rgba[invalid] = [90, 90, 110, 190]
    return rgba


def calculate_hotspot_coordinates(
    bbox: list[float],
    mask: npt.NDArray[np.bool_],
    ndre_arr: npt.NDArray[np.float32],
) -> tuple[float, float] | None:
    """Eng past NDRE (xlorofill eng ko'p parchalangan) nuqtasining haqiqiy geografik koordinatasi (lat, lon) ni hisoblaydi."""
    if not np.any(mask):
        return None
    ndre_valid = np.where(mask, ndre_arr, np.nan)
    min_idx = int(np.nanargmin(ndre_valid))
    h, w = ndre_arr.shape
    exact_y, exact_x = np.unravel_index(min_idx, (h, w))

    min_lon, min_lat, max_lon, max_lat = bbox
    center_lat = min_lat + ((h - 1 - exact_y) / max(1, h - 1)) * (max_lat - min_lat)
    center_lon = min_lon + (exact_x / max(1, w - 1)) * (max_lon - min_lon)
    return round(float(center_lat), 6), round(float(center_lon), 6)


def generate_colormap_base64(rgba: npt.NDArray[np.uint8]) -> str:
    """RGBA massivini xotirada Base64 PNG Data URL ga aylantiradi."""
    img = Image.fromarray(rgba, mode="RGBA")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG", optimize=True)
    b64_str = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{b64_str}"



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
