"""5-Bosqichli Biofizik Anomaliyalarni Aniqlash va Differensial Qarorlar Modeli.

Copernicus Sentinel-2 L2A spektral kanallari (B02, B03, B04, B05, B08, B8A, B11)
asosida dala maydonidagi anomaliyalarni aniqlash, klasterlash, 8 zonal yo'nalish,
E egat anizotropiya koeffitsiyenti va 4 bosqichli differensial qarorlar daraxti.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import numpy.typing as npt
import scipy.ndimage

logger = logging.getLogger(__name__)

FloatArray = npt.NDArray[np.float32]
BoolArray = npt.NDArray[np.bool_]


@dataclass(frozen=True)
class AnomalyCluster:
    cluster_id: int
    pixel_count: int
    area_m2: float
    area_ha: float
    risk_level: str  # "CRITICAL", "HIGH", "MODERATE"
    compass_sector: str  # "Shimoliy", "Shimoli-sharqiy", "Sharqiy", etc.
    centroid_row: float
    centroid_col: float
    e_anisotropy: float
    orientation_type: str  # "linear_furrow" | "concentric_radial"
    orientation_label: str
    diagnosis_title: str
    diagnosis_code: str
    pathogen_name: str | None
    recommended_treatment: str
    agrotechnical_action: str
    mean_ndvi: float
    mean_savi: float
    mean_ndre: float
    mean_bri: float
    mean_ndwi: float
    mean_ndsi: float
    mean_delta_t: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AnomalyAnalysisReport:
    total_anomalous_pixels: int
    total_anomalous_area_ha: float
    anomaly_percentage: float
    cluster_count: int
    top_clusters: list[AnomalyCluster]
    field_metrics_summary: dict[str, dict[str, float]]
    historical_ndre_before_ndwi_drop: bool
    overall_health_verdict: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_anomalous_pixels": self.total_anomalous_pixels,
            "total_anomalous_area_ha": round(self.total_anomalous_area_ha, 3),
            "anomaly_percentage": round(self.anomaly_percentage, 2),
            "cluster_count": self.cluster_count,
            "top_clusters": [c.to_dict() for c in self.top_clusters],
            "field_metrics_summary": self.field_metrics_summary,
            "historical_ndre_before_ndwi_drop": self.historical_ndre_before_ndwi_drop,
            "overall_health_verdict": self.overall_health_verdict,
        }


def _safe_ratio(num: FloatArray, den: FloatArray, valid: BoolArray, fill: float = 0.0) -> FloatArray:
    """Nolga bo'lishdan xavfsiz nisbat hisoblash."""
    res = np.full(num.shape, fill, dtype=np.float32)
    safe = valid & np.isfinite(num) & np.isfinite(den) & (den != 0)
    np.divide(num, den, out=res, where=safe)
    return res


def compute_biophysical_indices(
    bands: dict[str, FloatArray], valid: BoolArray
) -> dict[str, FloatArray]:
    """10+ Biofizik Spektral Indekslarni hisoblaydi."""
    b2 = bands.get("B02", np.zeros_like(valid, dtype=np.float32))
    b3 = bands.get("B03", np.zeros_like(valid, dtype=np.float32))
    b4 = bands.get("B04", np.zeros_like(valid, dtype=np.float32))
    b5 = bands.get("B05", np.zeros_like(valid, dtype=np.float32))
    b8 = bands.get("B08", np.zeros_like(valid, dtype=np.float32))
    b8a = bands.get("B8A", b8)
    b11 = bands.get("B11", np.zeros_like(valid, dtype=np.float32))

    # 1. Biomassa va zichlik
    ndvi = _safe_ratio(b8 - b4, b8 + b4, valid, fill=0.0)
    ndvi = np.clip(ndvi, -1.0, 1.0)

    savi_den = b8 + b4 + 0.5
    savi = np.full_like(ndvi, 0.0)
    safe_savi = valid & (savi_den != 0)
    savi[safe_savi] = ((b8[safe_savi] - b4[safe_savi]) / savi_den[safe_savi]) * 1.5
    savi = np.clip(savi, -1.0, 1.5)

    evi_den = b8 + 6.0 * b4 - 7.5 * b2 + 1.0
    evi = np.full_like(ndvi, 0.0)
    safe_evi = valid & (evi_den != 0)
    evi[safe_evi] = (2.5 * (b8[safe_evi] - b4[safe_evi])) / evi_den[safe_evi]
    evi = np.clip(evi, -1.0, 1.5)

    lai = np.clip(3.618 * evi - 0.118, 0.0, 8.0)

    # 2. Xlorofill degradatsiyasi va azot
    ndre = _safe_ratio(b8a - b5, b8a + b5, valid, fill=0.0)
    ndre = np.clip(ndre, -1.0, 1.0)

    bri = _safe_ratio(b2, b4 + 1e-4, valid, fill=1.0)
    bri = np.clip(bri, 0.0, 5.0)

    lci = _safe_ratio(b8a - b5, b8a + b4 + 1e-4, valid, fill=0.0)
    lci = np.clip(lci, -1.0, 1.0)

    # 3. Suv balansi va barg namligi
    ndwi = _safe_ratio(b8a - b11, b8a + b11, valid, fill=0.0)
    ndwi = np.clip(ndwi, -1.0, 1.0)

    ndmi = _safe_ratio(b8 - b11, b8 + b11, valid, fill=0.0)
    ndmi = np.clip(ndmi, -1.0, 1.0)

    msi = _safe_ratio(b11, b8 + 1e-4, valid, fill=1.0)
    msi = np.clip(msi, 0.0, 5.0)

    # 4. Tuproq sho'rlanishi va tuproq indeksi
    ndsi = _safe_ratio(b3 - b11, b3 + b11, valid, fill=0.0)
    ndsi = np.clip(ndsi, -1.0, 1.0)

    bsi_num = (b11 + b4) - (b8 + b2)
    bsi_den = (b11 + b4) + (b8 + b2)
    bsi = _safe_ratio(bsi_num, bsi_den, valid, fill=0.0)
    bsi = np.clip(bsi, -1.0, 1.0)

    # 5. O'simlik harorati (Delta T transpiratsiya proxy)
    # Transpiratsiya to'xtaganda barg harorati +3...+6C qiziydi
    delta_t = np.clip((1.0 - ndwi) * (1.0 - ndvi) * 6.0, 0.0, 6.0)

    return {
        "NDVI": ndvi,
        "SAVI": savi,
        "EVI": evi,
        "LAI": lai,
        "NDRE": ndre,
        "BRI": bri,
        "LCI": lci,
        "NDWI": ndwi,
        "NDMI": ndmi,
        "MSI": msi,
        "NDSI": ndsi,
        "BSI": bsi,
        "Delta_T": delta_t,
    }


def compute_metrics_distribution(
    indices: dict[str, FloatArray], valid: BoolArray
) -> dict[str, dict[str, float]]:
    """Dala bo'yicha har bir indeksning Min, Mean, Median, Max, Std statistikasini hisoblaydi."""
    summary: dict[str, dict[str, float]] = {}
    for name, arr in indices.items():
        vals = arr[valid & np.isfinite(arr)]
        if vals.size == 0:
            summary[name] = {"min": 0.0, "mean": 0.0, "median": 0.0, "max": 0.0, "std": 0.0}
        else:
            summary[name] = {
                "min": round(float(np.min(vals)), 3),
                "mean": round(float(np.mean(vals)), 3),
                "median": round(float(np.median(vals)), 3),
                "max": round(float(np.max(vals)), 3),
                "std": round(float(np.std(vals)), 3),
            }
    return summary


def determine_compass_sector(
    cluster_row: float, cluster_col: float, field_center_row: float, field_center_col: float
) -> str:
    """8 tomonlama kompas sektorini aniqlaydi (Shimoliy, Janubiy, Sharqiy va h.k.)."""
    # Matritsada row pastga qarab o'sadi, shuning uchun delta_y = field_center_row - cluster_row (yuqoriga musbat)
    dy = field_center_row - cluster_row
    dx = cluster_col - field_center_col

    dist = np.hypot(dy, dx)
    if dist < 1.5:
        return "Markaziy"

    angle_deg = np.degrees(np.arctan2(dy, dx))  # [-180, 180], 0 = Sharq, 90 = Shimol
    if angle_deg < 0:
        angle_deg += 360  # [0, 360]

    # Sektorlar: 0: Sharq, 45: Shimoli-sharq, 90: Shimol, 135: Shimoli-g'arb,
    # 180: G'arb, 225: Janubi-g'arb, 270: Janub, 315: Janubi-sharq
    if 22.5 <= angle_deg < 67.5:
        return "Shimoli-sharqiy"
    if 67.5 <= angle_deg < 112.5:
        return "Shimoliy"
    if 112.5 <= angle_deg < 157.5:
        return "Shimoli-g'arbiy"
    if 157.5 <= angle_deg < 202.5:
        return "G'arbiy"
    if 202.5 <= angle_deg < 247.5:
        return "Janubi-g'arbiy"
    if 247.5 <= angle_deg < 292.5:
        return "Janubiy"
    if 292.5 <= angle_deg < 337.5:
        return "Janubi-sharqiy"
    return "Sharqiy"


def compute_furrow_anisotropy(
    rows: np.ndarray, cols: np.ndarray
) -> tuple[float, str, str]:
    """Kovariatsiya matritsasi xos qiymatlaridan E koeffitsiyenti va shaklni hisoblaydi."""
    if len(rows) < 3:
        return 1.0, "concentric_radial", "Konsentrik doirasimon (Radial / Lokal o'choq)"

    coords = np.column_stack([rows, cols])
    cov = np.cov(coords, rowvar=False)

    try:
        eigenvalues, _ = np.linalg.eigh(cov)
        lambda_min = max(0.0, float(min(eigenvalues)))
        lambda_max = max(0.0, float(max(eigenvalues)))
        e_val = float(np.sqrt(lambda_max / (lambda_min + 1e-4)))
    except Exception:
        e_val = 1.0

    e_val = round(e_val, 2)
    if e_val > 3.0:
        return e_val, "linear_furrow", "Egat bo'ylab cho'zilgan (Chiziqli / Oqim yo'nalishida)"
    return e_val, "concentric_radial", "Konsentrik doirasimon (Radial / Lokal o'choq)"


def evaluate_differential_diagnosis(
    cluster_means: dict[str, float],
    historical_ndre_before_ndwi_drop: bool,
    crop_name: str = "Ekin",
) -> tuple[str, str, str | None, str, str, str]:
    """4 Bosqichli Differensial Qarorlar Modeli.

    Returns:
        (risk_level, diagnosis_title, diagnosis_code, pathogen_name, recommended_treatment, agrotechnical_action)
    """
    ndsi = cluster_means.get("NDSI", 0.0)
    savi = cluster_means.get("SAVI", 0.0)
    ndre = cluster_means.get("NDRE", 0.0)
    bri = cluster_means.get("BRI", 1.0)
    ndwi = cluster_means.get("NDWI", 0.0)
    ndvi = cluster_means.get("NDVI", 0.0)

    crop_lower = crop_name.lower()

    # 1-BOSQICH: Tuproq Sho'rlanishi va Osmotik Stress Filtri
    if ndsi >= 0.38 and savi < 0.30:
        return (
            "CRITICAL",
            "Osmotik Sho'rlanish Stressi",
            "SALINITY_OSMOTIC_STRESS",
            None,
            "Sho'r yuvish uchun zovur va kollektorlar chuqurlashtirilsin. "
            "Gips yoki fosfogips (3-4 t/ga) kiritish, tuproq tuz balansini tiklash tavsiya etiladi.",
            "Oddiy sug'orish sho'rlanishni kuchaytirishi mumkin. "
            "Mavsumdan keyin 3500-4000 m3/ga me'yorda qishki/bahorgi sho'r yuvish o'tkazilsin.",
        )

    # 2-BOSQICH: Erta Zamburug'li Zararlanish Filtri
    if ndre < 0.45 and bri > 1.20 and ndwi >= 0.38:
        if "paxta" in crop_lower or "cotton" in crop_lower:
            pathogen = "Verticillium dahliae (Erta Vilt) yoki Xanthomonas malvacearum"
            treatment = "Topsin-M (1.5 kg/ga) yoki Fundazol (1.0 kg/ga) purkash, poyadan oziqlantirish."
        elif "bug'doy" in crop_lower or "g'alla" in crop_lower or "wheat" in crop_lower:
            pathogen = "Puccinia striiformis (Sariq Zang) yoki Septoria tritici"
            treatment = "Amistar Trio (0.6-0.8 l/ga) yoki Falcon (0.6 l/ga) fungitsidini zudlik bilan qo'llash."
        else:
            pathogen = "Phytophthora infestans yoki Fusarium zamburug'lari"
            treatment = "Ridomil Gold (2.5 kg/ga) yoki Quadris (0.8 l/ga) bilan profilaktik ishlov berish."

        return (
            "HIGH",
            "Erta Zamburug'li Zararlanish (Erta Vilt / Sariq Zang / Fitoftora)",
            "EARLY_FUNGAL_INFECTION",
            pathogen,
            f"Zudlik bilan fungitsid bilan ishlov berilsin: {treatment}",
            "Barglarda suv saqlangan holda xlorofill tez parchalanmoqda. "
            "Suv berishni vaqtincha to'xtatib, o'choq atrofini fungitsidli himoya qobig'i bilan qamrab oling.",
        )

    # 3-BOSQICH: 60 Kunlik Vaqt Dinamikasi & Ksilema Blokadasi
    if ndwi < 0.25 and ndre < 0.40:
        if historical_ndre_before_ndwi_drop:
            pathogen = "Verticillium dahliae yoki Fusarium oxysporum (Sekundar Vilt)"
            return (
                "CRITICAL",
                "Kechki Patogen (Sekundar Ksilema Naylari Blokadasi / Ilg'or Vilt)",
                "XYLEM_BLOCKADE_ADVANCED_PATHOGEN",
                pathogen,
                "Benomil (1.5 kg/ga) yoki Topsin-M (1.5 kg/ga) bilan ildizdan va bargdan kompleks ishlov berish.",
                "Patogen o'simlik poyasi ksilema naylarini to'sib qo'ygan, o'simlik ichidan qurimoqda. "
                "Zararlangan tana qoldiqlarini daladan chiqarish va kaliyli o'g'it (K2O 50 kg/ga) berish zarur.",
            )
        return (
            "HIGH",
            "Sof Gidro-Stress (Sug'orish Yetishmovchiligi)",
            "HYDRO_STRESS_IRRIGATION_DEFICIT",
            None,
            "Dalaning ushbu sektoriga navbatdagi sug'orish suvini 700-800 m3/ga me'yorda zudlik bilan yetkazish.",
            "Xlorofill holati barqaror, faqat dalaga suv yetib bormagan. "
            "Egatlar bo'ylab suv oqimini to'g'rilang; sug'orilgach 5 kunda to'qimalar turgori tiklanadi.",
        )

    # 4-BOSQICH: Oziqlanish va Boshqa Stresslar
    if ndre < 0.35 and ndwi >= 0.30:
        return (
            "MODERATE",
            "Azot va Mikroelementlar Tanqisligi",
            "NUTRIENT_NITROGEN_DEFICIENCY",
            None,
            "Karbamid (15-20 kg/ga) yoki bargdan kompleks mikroo'g'itlar (Rux, Magniy, Temir xelati) purkash.",
            "Azot o'zlashtirilishi susaygan. Bargdan suspenziya usulida oziqlantirish orqali fotosintez tiklansin.",
        )

    if ndvi < 0.45:
        return (
            "MODERATE",
            "Mo'tadil Vegetatsiya Zaiflashuvi",
            "MODERATE_VEGETATION_DECLINE",
            None,
            "Bargdan o'stiruvchi stimulyatorlar (Gumat, Aminokislotalar) bilan oziqlantirish.",
            "Begona o'tlarga qarshi kultivatsiya o'tkazish va tuproq yumshatilishini ta'minlash.",
        )

    return (
        "LOW",
        "Lokal Spektral Egrilik",
        "LOCAL_DEVIATION",
        None,
        "Profilaktik agrotexnik nazorat.",
        "Dala holatini navbatdagi Sentinel-2 o'tishida qayta kuzatib boring.",
    )


def detect_and_cluster_anomalies(
    bands: dict[str, FloatArray],
    valid_mask: BoolArray,
    *,
    historical_metrics: dict[str, list[dict[str, Any]]] | None = None,
    crop_name: str = "Ekin",
    pixel_size_m: float = 10.0,
) -> AnomalyAnalysisReport:
    """5-Bosqichli to'liq anomaliya tahlilini bajaradi."""
    indices = compute_biophysical_indices(bands, valid_mask)
    metrics_summary = compute_metrics_distribution(indices, valid_mask)

    ndvi = indices["NDVI"]
    ndre = indices["NDRE"]
    ndwi = indices["NDWI"]
    ndsi = indices["NDSI"]

    mean_ndvi = metrics_summary.get("NDVI", {}).get("mean", 0.50)

    # 3-BOSQICH: Piksel darajasidagi anomaliya mezoni
    # (NDVI < 0.55) or (NDVI < mean_ndvi - 0.10) or (NDRE < 0.48) or (NDWI < 0.28) or (NDSI > 0.38)
    anomaly_condition = (
        (ndvi < 0.55)
        | (ndvi < (mean_ndvi - 0.10))
        | (ndre < 0.48)
        | (ndwi < 0.28)
        | (ndsi > 0.38)
    )
    anomaly_pixels = valid_mask & anomaly_condition & np.isfinite(ndvi)

    total_valid = int(np.sum(valid_mask))
    total_anom = int(np.sum(anomaly_pixels))
    pixel_area_ha = (pixel_size_m * pixel_size_m) / 10000.0
    total_anom_ha = total_anom * pixel_area_ha
    anom_pct = (total_anom / total_valid * 100.0) if total_valid > 0 else 0.0

    # 8-Connectivity Klasterlash
    structure = np.ones((3, 3), dtype=int)
    labeled_array, num_features = scipy.ndimage.label(anomaly_pixels, structure=structure)

    # Tarixiy dinamikani tekshirish: NDRE avval tushganmi yoki NDWI?
    historical_ndre_before_ndwi_drop = False
    if historical_metrics:
        ndre_history = historical_metrics.get("NDRE", [])
        ndwi_history = historical_metrics.get("NDWI", [])
        if len(ndre_history) >= 2 and len(ndwi_history) >= 2:
            # So'nggi 2 ta kuzatuv o'zgarishi
            try:
                ndre_prev = float(ndre_history[-2].get("mean", 0.4))
                ndre_curr = float(ndre_history[-1].get("mean", 0.4))
                ndwi_prev = float(ndwi_history[-2].get("mean", 0.3))
                ndwi_curr = float(ndwi_history[-1].get("mean", 0.3))
                ndre_drop = ndre_prev - ndre_curr
                ndwi_drop = ndwi_prev - ndwi_curr
                if ndre_drop > 0.08 and ndwi_drop < 0.04:
                    historical_ndre_before_ndwi_drop = True
            except Exception:
                pass

    # Dala markazi (markaziy nuqta)
    valid_rows, valid_cols = np.where(valid_mask)
    if len(valid_rows) > 0:
        field_center_row = float(np.mean(valid_rows))
        field_center_col = float(np.mean(valid_cols))
    else:
        field_center_row = 0.0
        field_center_col = 0.0

    clusters: list[AnomalyCluster] = []
    for label_id in range(1, num_features + 1):
        cluster_mask = labeled_array == label_id
        cluster_pixels = int(np.sum(cluster_mask))

        # 2 pikseldan (< 200 m2) kichik shovqinlarni o'chirish
        if cluster_pixels < 2:
            continue

        c_rows, c_cols = np.where(cluster_mask)
        c_cent_row = float(np.mean(c_rows))
        c_cent_col = float(np.mean(c_cols))

        sector = determine_compass_sector(
            c_cent_row, c_cent_col, field_center_row, field_center_col
        )
        e_val, o_type, o_label = compute_furrow_anisotropy(c_rows, c_cols)

        # Klaster ichidagi o'rtacha indekslar
        c_means = {
            name: float(np.mean(arr[cluster_mask]))
            for name, arr in indices.items()
            if np.any(cluster_mask)
        }

        (
            risk,
            diag_title,
            diag_code,
            pathogen,
            treatment,
            action,
        ) = evaluate_differential_diagnosis(
            c_means, historical_ndre_before_ndwi_drop, crop_name=crop_name
        )

        cluster_area_m2 = cluster_pixels * (pixel_size_m * pixel_size_m)
        cluster_area_ha = cluster_area_m2 / 10000.0

        clusters.append(
            AnomalyCluster(
                cluster_id=label_id,
                pixel_count=cluster_pixels,
                area_m2=round(cluster_area_m2, 1),
                area_ha=round(cluster_area_ha, 3),
                risk_level=risk,
                compass_sector=sector,
                centroid_row=round(c_cent_row, 1),
                centroid_col=round(c_cent_col, 1),
                e_anisotropy=e_val,
                orientation_type=o_type,
                orientation_label=o_label,
                diagnosis_title=diag_title,
                diagnosis_code=diag_code,
                pathogen_name=pathogen,
                recommended_treatment=treatment,
                agrotechnical_action=action,
                mean_ndvi=round(c_means.get("NDVI", 0.0), 3),
                mean_savi=round(c_means.get("SAVI", 0.0), 3),
                mean_ndre=round(c_means.get("NDRE", 0.0), 3),
                mean_bri=round(c_means.get("BRI", 1.0), 3),
                mean_ndwi=round(c_means.get("NDWI", 0.0), 3),
                mean_ndsi=round(c_means.get("NDSI", 0.0), 3),
                mean_delta_t=round(c_means.get("Delta_T", 0.0), 2),
            )
        )

    # Tartiblash: CRITICAL > HIGH > MODERATE > LOW, so'ng maydoni bo'yicha
    risk_weights = {"CRITICAL": 3, "HIGH": 2, "MODERATE": 1, "LOW": 0}
    clusters.sort(
        key=lambda c: (risk_weights.get(c.risk_level, 0), c.pixel_count),
        reverse=True,
    )

    top_5 = clusters[:5]

    # Umumiy xulosa
    if not top_5 or anom_pct < 5.0:
        verdict = f"{crop_name} maydonida jiddiy biofizik anomaliya o'choqlari aniqlanmadi, vegetatsiya barqaror."
    elif any(c.risk_level == "CRITICAL" for c in top_5):
        verdict = f"{crop_name} maydonida o'ta xavfli (CRITICAL) o'choqlar aniqlandi. Zudlik bilan agrotexnik choralar talab etiladi."
    else:
        verdict = f"{crop_name} maydonida lokal stress o'choqlari mavjud, nazorat va differensial parvarish zarur."

    return AnomalyAnalysisReport(
        total_anomalous_pixels=total_anom,
        total_anomalous_area_ha=total_anom_ha,
        anomaly_percentage=anom_pct,
        cluster_count=len(clusters),
        top_clusters=top_5,
        field_metrics_summary=metrics_summary,
        historical_ndre_before_ndwi_drop=historical_ndre_before_ndwi_drop,
        overall_health_verdict=verdict,
    )
