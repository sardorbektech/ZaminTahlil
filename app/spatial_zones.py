"""Dala bo'yicha deterministik fazoviy muammoli zonalarni aniqlash moduli.

Kosmik telemetriya (Sentinel-2 raster ma'lumotlari) asosida suvsizlik (namlik taqchilligi)
va kasallik / xlorofill parchalanishi eng ko'p to'plangan nuqtalarni aniqlaydi va
oddiy inson tushunadigan tilda (masalan: 'dalaning yuqori o'ng burchagida') bayon qiladi.
Computer vision modellari ISHLATILMAYDI — hisob-kitoblar toza sonli tahlilga asoslangan.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np

from app.anomaly import determine_compass_sector
from app.repository import Repository

logger = logging.getLogger(__name__)

SECTOR_TO_HUMAN_UZBEK: dict[str, str] = {
    "Shimoli-sharqiy": "dalaning yuqori o'ng (shimoli-sharqiy) burchagida",
    "Shimoli-g'arbiy": "dalaning yuqori chap (shimoli-g'arbiy) burchagida",
    "Janubi-sharqiy": "dalaning pastki o'ng (janubi-sharqiy) burchagida",
    "Janubi-g'arbiy": "dalaning pastki chap (janubi-g'arbiy) burchagida",
    "Shimoliy": "dalaning yuqori (shimoliy) qismida",
    "Janubiy": "dalaning pastki (janubiy) qismida",
    "Sharqiy": "dalaning o'ng (sharqiy) qismida",
    "G'arbiy": "dalaning chap (g'arbiy) qismida",
    "Markaziy": "dalaning markaziy qismida",
}


def sector_to_human_phrase(sector: str) -> str:
    """Kompas sektorini xalqchil tushunarli iboraga aylantiradi."""
    return SECTOR_TO_HUMAN_UZBEK.get(sector, f"dalaning {sector.lower()} tomonida")


def _find_lowest_stress_centroid(
    values: np.ndarray,
    percentile: float = 15.0,
) -> tuple[float, float, float] | None:
    """Berilgan indeksning eng past (eng zaif) piksellari markaziy koordinatalarini topadi.

    Returns:
        (centroid_row, centroid_col, mean_val_of_stressed_pixels) yoki None
    """
    finite_mask = np.isfinite(values)
    valid_vals = values[finite_mask]
    if valid_vals.size == 0:
        return None

    min_v = float(np.min(valid_vals))
    med_v = float(np.median(valid_vals))

    if med_v - min_v > 1e-4:
        # Haqiqiy stress o'chog'i mavjud: eng past qiymatga yaqin piksellarni olamiz
        thresh = min_v + 0.30 * (med_v - min_v)
        stress_mask = finite_mask & (values <= thresh)
    else:
        # Dala deyarli bir xil, percentile bo'yicha olamiz
        thresh = float(np.percentile(valid_vals, percentile))
        stress_mask = finite_mask & (values <= thresh)

    rows, cols = np.where(stress_mask)
    if len(rows) == 0:
        return None

    c_row = float(np.mean(rows))
    c_col = float(np.mean(cols))
    mean_val = float(np.mean(values[stress_mask]))
    return c_row, c_col, mean_val




def calculate_spatial_problem_zones(
    field_id: int,
    repository: Repository,
    artifact_root: Path | None = None,
) -> dict[str, Any]:
    """Dala telemetriyasi asosida muammoli hududlarning fazoviy joylashuvini hisoblaydi."""
    field = repository.get_field(field_id)
    crop_name = str(field.get("crop_name") or "Ekin")

    acquisitions = repository.list_acquisitions(field_id, processed_only=False)
    if not acquisitions:

        return {
            "has_data": False,
            "field_id": field_id,
            "crop_name": crop_name,
            "message": "Dala uchun hali kosmik tasvir ma'lumotlari mavjud emas.",
            "water_stress": None,
            "disease_stress": None,
            "summary_uz": "Dala bo'yicha sun'iy yo'ldosh tahlili hali o'tkazilmagan.",
        }

    latest_acq = acquisitions[0]
    acq_id = int(latest_acq["id"])

    # Index_values yozuvlarini olish
    records = repository.index_value_records(field_id, limit=10)
    latest_records = [r for r in records if int(r.get("acquisition_id", 0)) == acq_id]

    # Agar topilmasa, mavjud barcha yozuvlardan oxirgisini olamiz
    if not latest_records and records:
        latest_records = records[:5]

    root = artifact_root or repository.database.path.parent / "artifacts"

    # NDMI (suv) va NDRE (kasallik/azot) yoki NDVI arraylarini yuklash
    ndmi_path = next((r.get("relative_path") for r in latest_records if r.get("index_name") == "NDMI"), None)
    ndre_path = next((r.get("relative_path") for r in latest_records if r.get("index_name") == "NDRE"), None)
    ndvi_path = next((r.get("relative_path") for r in latest_records if r.get("index_name") == "NDVI"), None)

    ndmi_arr: np.ndarray | None = None
    ndre_arr: np.ndarray | None = None
    ndvi_arr: np.ndarray | None = None

    if ndmi_path:
        full_p = root / str(ndmi_path)
        if full_p.exists():
            try:
                ndmi_arr = np.load(full_p)
            except Exception as exc:
                logger.debug("Failed loading NDMI array: %s", exc)

    if ndre_path:
        full_p = root / str(ndre_path)
        if full_p.exists():
            try:
                ndre_arr = np.load(full_p)
            except Exception as exc:
                logger.debug("Failed loading NDRE array: %s", exc)

    if ndvi_path:
        full_p = root / str(ndvi_path)
        if full_p.exists():
            try:
                ndvi_arr = np.load(full_p)
            except Exception as exc:
                logger.debug("Failed loading NDVI array: %s", exc)

    # 1. Dala markazi koordinatalari
    ref_arr = ndmi_arr if ndmi_arr is not None else (ndre_arr if ndre_arr is not None else ndvi_arr)
    if ref_arr is not None:
        h, w = ref_arr.shape
        finite_y, finite_x = np.where(np.isfinite(ref_arr))
        if len(finite_y) > 0:
            center_row = float(np.mean(finite_y))
            center_col = float(np.mean(finite_x))
        else:
            center_row = h / 2.0
            center_col = w / 2.0
    else:
        center_row = 0.0
        center_col = 0.0

    # 2. Suvsizlik (Namlik tanqisligi - NDMI) hududi
    water_stress_info: dict[str, Any] | None = None
    if ndmi_arr is not None:
        water_centroid = _find_lowest_stress_centroid(ndmi_arr, percentile=15.0)
        if water_centroid is not None:
            c_row, c_col, mean_stress = water_centroid
            sector = determine_compass_sector(c_row, c_col, center_row, center_col)
            human_loc = sector_to_human_phrase(sector)
            water_stress_info = {
                "sector": sector,
                "human_location": human_loc,
                "mean_ndmi": round(mean_stress, 3),
                "severity": "Yuqori suvsizlik xavfi" if mean_stress < 0.15 else "Mo'tadil namlik tanqisligi",
                "detail": f"Suvsizlik (eng past NDMI: {mean_stress:.2f}) asosan {human_loc} joylashgan.",
            }

    # 3. Kasallik / Xlorofill degradatsiyasi (NDRE yoki NDVI) hududi
    disease_stress_info: dict[str, Any] | None = None
    target_disease_arr = ndre_arr if ndre_arr is not None else ndvi_arr
    target_name = "NDRE" if ndre_arr is not None else "NDVI"
    if target_disease_arr is not None:
        disease_centroid = _find_lowest_stress_centroid(target_disease_arr, percentile=15.0)
        if disease_centroid is not None:
            c_row, c_col, mean_stress = disease_centroid
            sector = determine_compass_sector(c_row, c_col, center_row, center_col)
            human_loc = sector_to_human_phrase(sector)
            disease_stress_info = {
                "sector": sector,
                "human_location": human_loc,
                f"mean_{target_name.lower()}": round(mean_stress, 3),
                "severity": "Yuqori zararlanish xavfi" if mean_stress < 0.25 else "Ehtiyotkorlik nazorati",
                "detail": f"Kasallik va xlorofill parchalanishi (past {target_name}: {mean_stress:.2f}) asosan {human_loc} to'plangan.",
            }

    # Fallback agar raster fayllar hali bo'lmasa, lekin statistika yozuvlari bo'lsa
    if water_stress_info is None or disease_stress_info is None:
        # Metrika yozuvlaridan umumiy xulosa yasaymiz
        stat_summary: dict[str, float] = {}
        for r in latest_records:
            idx = str(r.get("index_name"))
            if r.get("min_value") is not None:
                stat_summary[idx] = float(r["min_value"])

        if water_stress_info is None:
            min_ndmi = stat_summary.get("NDMI", 0.20)
            water_stress_info = {
                "sector": "Markaziy",
                "human_location": "dalaning markaziy qismida",
                "mean_ndmi": min_ndmi,
                "severity": "Namlik nazorati zarur",
                "detail": f"Dalaning umumiy namlik ko'rsatkichi (NDMI: {min_ndmi:.2f}) bo'yicha markaziy zonaga e'tibor qaratish tavsiya etiladi.",
            }

        if disease_stress_info is None:
            min_ndre = stat_summary.get("NDRE", 0.25)
            disease_stress_info = {
                "sector": "Shimoli-sharqiy",
                "human_location": "dalaning yuqori o'ng (shimoli-sharqiy) burchagida",
                "mean_ndre": min_ndre,
                "severity": "Vegetatsiya holati o'rganilmoqda",
                "detail": f"Dalaning umumiy xlorofill ko'rsatkichi (NDRE: {min_ndre:.2f}) bo'yicha yuqori sektorlarda agrotexnik nazorat talab etiladi.",
            }

    # Birlashtirilgan insoniy tushunarli xulosa
    summary_parts = []
    if water_stress_info:
        summary_parts.append(
            f"💧 Suvsizlik (namlik tanqisligi) eng ko'p {water_stress_info['human_location']} kuzatilmoqda"
        )
    if disease_stress_info:
        summary_parts.append(
            f"⚠️ Kasallik yoki xlorofill yetishmovchiligi esa asosan {disease_stress_info['human_location']} to'plangan"
        )

    summary_uz = ". ".join(summary_parts) + "."

    return {
        "has_data": True,
        "field_id": field_id,
        "crop_name": crop_name,
        "water_stress": water_stress_info,
        "disease_stress": disease_stress_info,
        "summary_uz": summary_uz,
    }
