import glob
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

FEATURE_DESCRIPTIONS: dict[str, str] = {
    "s2_ndvi_mean": "O'rtacha NDVI (Biomassa va yashillik holati)",
    "s2_ndvi_max": "Maksimal NDVI (Eng yuqori vegetatsiya cho'qqisi)",
    "s2_evi_mean": "Rivojlangan vegetatsiya indeksi (EVI)",
    "s2_ndre_mean": "Qizil chegara xlorofill indeksi (NDRE)",
    "s2_ndmi_mean": "Barglardagi suv va namlik miqdori (NDMI)",
    "s1_vh_mean": "Sentinel-1 VH radar sochilishi (Poya/Biomassa zichligi)",
    "s1_vv_mean": "Sentinel-1 VV radar sochilishi (Tuproq va namlik)",
    "s1_vv_vh_ratio_mean": "Radar polarizatsiyalar farqi (VV - VH)",
    "weather_temperature_2m_mean": "Oylik o'rtacha havo harorati (2m)",
    "weather_temperature_2m_range": "Kunlik harorat amplitudasi (Tmax - Tmin)",
    "weather_total_precipitation_sum": "Oylik jami yog'ingarchilik miqdori (mm)",
    "weather_rain_sum": "Oylik jami yomg'ir miqdori (mm)",
    "weather_soil_moisture_0_7cm_mean": "0-7 sm yuqori qatlam tuproq namligi",
    "weather_soil_moisture_7_28cm_mean": "7-28 sm ildiz qatlami tuproq namligi",
    "weather_soil_moisture_28_100cm_mean": "28-100 sm chuqur qatlam tuproq namligi",
    "weather_soil_temperature_0_7cm_mean": "Tuproq sirti harorati (0-7 sm)",
    "weather_evapotranspiration_et0_sum": "Oylik bug'lanish miqdori (ET0, mm)",
    "weather_water_balance_sum": "Oylik gidrologik suv balansi (Yog'in - ET0)",
    "weather_shortwave_radiation_sum": "Jami quyosh radiatsiyasi (MJ/m2)",
    "weather_rainy_days_count": "Yog'ingarchilikli kunlar soni",
    "crop_age_days": "Ekinning ekilgandan beri yoshi (kun)",
    "season_progress_ratio": "Mavsum rivojlanish ulushi (0.0 - 1.0)",
    "days_to_harvest": "Hosil yig'im-terimigacha qolgan kunlar",
    "month_sin": "Kuzatuv oyi davriyligi (Sinus)",
    "month_cos": "Kuzatuv oyi davriyligi (Kosinus)",
}

CROP_CALENDARS: dict[str, dict[str, Any]] = {
    "cotton": {
        "name": "Paxta (G‘o‘za)",
        "planting_date": "2026-04-15",
        "harvest_date": "2026-10-15",
        "season_start": "2026-04-01",
        "season_end": "2026-10-31",
        "description": "O'zbekiston sharoitida paxtaning faol vegetatsiya va hosil to'plash davri",
    },
    "wheat": {
        "name": "Kuzgi Bug‘doy",
        "planting_date": "2025-10-15",
        "harvest_date": "2026-06-25",
        "season_start": "2025-10-01",
        "season_end": "2026-06-30",
        "description": "Kuzgi bug'doyning tuplanish, naychalash, boshoqlash va pishish bosqichlari",
    },
}


@dataclass(frozen=True)
class FeatureImportanceItem:
    feature: str
    importance: float
    description: str


@dataclass(frozen=True)
class PhenologyDataPoint:
    month: int
    ndvi: float
    evi: float
    ndre: float
    ndmi: float
    s1_vh: float
    s1_vv_vh: float
    temp_mean: float
    rain_sum: float
    soil_moisture: float


@dataclass(frozen=True)
class YieldPredictionResult:
    crop: str
    crop_display_name: str
    model_used: str
    predicted_yield_t_ha: float
    yield_min_expected: float
    yield_max_expected: float
    total_expected_yield_tons: float
    total_yield_min_tons: float
    total_yield_max_tons: float
    field_area_ha: float
    top_features: list[FeatureImportanceItem]
    phenology_timeline: list[PhenologyDataPoint]
    features_count: int
    execution_time_sec: float


def normalize_crop_name(crop_name: str) -> str:
    """O'simlik nomini paxta yoki bug'doy toifasiga moslaydi."""
    lowered = crop_name.lower().strip()
    if any(k in lowered for k in ("paxta", "cotton", "g'o'za", "goza", "g‘o‘za")):
        return "cotton"
    if any(k in lowered for k in ("bug'doy", "bugdoy", "wheat", "bug‘doy", "don", "arpa")):
        return "wheat"
    return "cotton"


def process_raw_observations(
    df_s2: pd.DataFrame,
    df_s1: pd.DataFrame,
    df_w: pd.DataFrame,
    planting_date: str,
    harvest_date: str,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """1-qadam: Spektral indekslar, radar nisbatlari va fenologiyani hisoblash."""
    df_s2 = df_s2.copy()
    df_s1 = df_s1.copy()
    df_w = df_w.copy()

    df_s2["year_month"] = df_s2["date"].dt.strftime("%Y-%m")
    df_s1["year_month"] = df_s1["date"].dt.strftime("%Y-%m")
    df_w["year_month"] = df_w["date"].dt.strftime("%Y-%m")

    eps = 1e-8
    b02 = df_s2.get("s2_b02_blue", pd.Series(0.05, index=df_s2.index))
    b03 = df_s2.get("s2_b03_green", pd.Series(0.08, index=df_s2.index))
    b04 = df_s2.get("s2_b04_red", pd.Series(0.06, index=df_s2.index))
    b05 = df_s2.get("s2_b05_red_edge_1", pd.Series(0.12, index=df_s2.index))
    b08 = df_s2.get("s2_b08_nir", pd.Series(0.35, index=df_s2.index))
    b11 = df_s2.get("s2_b11_swir_1", pd.Series(0.18, index=df_s2.index))

    s2_indices = {
        "s2_ndvi": (b08 - b04) / (b08 + b04 + eps),
        "s2_evi": 2.5 * ((b08 - b04) / (b08 + 6.0 * b04 - 7.5 * b02 + 1.0 + eps)),
        "s2_gndvi": (b08 - b03) / (b08 + b03 + eps),
        "s2_savi": 1.5 * ((b08 - b04) / (b08 + b04 + 0.5 + eps)),
        "s2_msavi": (
            2.0 * b08
            + 1.0
            - np.sqrt(np.clip((2.0 * b08 + 1.0) ** 2 - 8.0 * (b08 - b04), 0, None))
        )
        / 2.0,
        "s2_osavi": (b08 - b04) / (b08 + b04 + 0.16 + eps),
        "s2_ndre": (b08 - b05) / (b08 + b05 + eps),
        "s2_ci_red_edge": (b08 / (b05 + eps)) - 1.0,
        "s2_ndwi": (b03 - b08) / (b03 + b08 + eps),
        "s2_ndmi": (b08 - b11) / (b08 + b11 + eps),
    }
    for col_name, col_data in s2_indices.items():
        df_s2[col_name] = col_data

    # S1 radar nisbatlari
    if "s1_vv" in df_s1.columns and "s1_vh" in df_s1.columns:
        df_s1["s1_vv_vh_ratio"] = df_s1["s1_vv"] - df_s1["s1_vh"]
    else:
        df_s1["s1_vv"] = -11.0
        df_s1["s1_vh"] = -16.0
        df_s1["s1_vv_vh_ratio"] = 5.0

    # Fenologiya
    p_dt = pd.to_datetime(planting_date)
    h_dt = pd.to_datetime(harvest_date)
    total_season_days = max((h_dt - p_dt).days, 1)

    w_feats = {
        "weather_water_balance": df_w.get("weather_total_precipitation", 0)
        - df_w.get("weather_evapotranspiration_et0", 0),
        "crop_age_days": (df_w["date"] - p_dt).dt.days.clip(lower=0),
        "days_to_harvest": (h_dt - df_w["date"]).dt.days.clip(lower=0),
        "season_progress_ratio": (
            (df_w["date"] - p_dt).dt.days.clip(lower=0) / total_season_days
        ).clip(0.0, 1.0),
        "is_rainy_day": (df_w.get("weather_total_precipitation", 0) >= 0.1).astype(int),
    }
    for col_name, col_data in w_feats.items():
        df_w[col_name] = col_data

    return df_s2, df_s1, df_w


def build_monthly_ml_features(
    df_s2: pd.DataFrame,
    df_s1: pd.DataFrame,
    df_w: pd.DataFrame,
    target_year: int = 2026,
) -> pd.DataFrame:
    """2-qadam: Oylik 122 ta ML parametrlar matritsasini qurish."""
    if "latitude" not in df_w.columns:
        df_w["latitude"] = 40.0
    if "longitude" not in df_w.columns:
        df_w["longitude"] = 65.0

    w_grouped = df_w.groupby("year_month")
    w_meta = w_grouped[["longitude", "latitude"]].first()

    temp_stats = w_grouped["weather_temperature_2m"].agg(
        weather_temperature_2m_mean="mean",
        weather_temperature_2m_min="min",
        weather_temperature_2m_max="max",
    )
    temp_stats["weather_temperature_2m_range"] = (
        temp_stats["weather_temperature_2m_max"] - temp_stats["weather_temperature_2m_min"]
    )

    app_temp_stats = w_grouped["weather_apparent_temperature"].agg(
        weather_apparent_temperature_mean="mean",
        weather_apparent_temperature_min="min",
        weather_apparent_temperature_max="max",
    )

    precip_stats = w_grouped["weather_total_precipitation"].agg(
        weather_total_precipitation_sum="sum",
        weather_total_precipitation_max="max",
        weather_total_precipitation_mean="mean",
    )
    rain_stats = w_grouped["weather_rain"].agg(
        weather_rain_sum="sum",
        weather_rain_max="max",
        weather_rain_mean="mean",
    )
    rainy_days = w_grouped["is_rainy_day"].sum().rename("weather_rainy_days_count")

    solar_stats = w_grouped["weather_shortwave_radiation"].agg(
        weather_shortwave_radiation_sum="sum",
        weather_shortwave_radiation_mean="mean",
    )

    wind_stats = w_grouped["weather_wind_speed_10m"].agg(
        weather_wind_speed_10m_mean="mean",
        weather_wind_speed_10m_max="max",
    )

    soil_temp_stats = w_grouped["weather_soil_temperature_0_7cm"].agg(
        weather_soil_temperature_0_7cm_mean="mean",
        weather_soil_temperature_0_7cm_min="min",
        weather_soil_temperature_0_7cm_max="max",
    )

    sm1_stats = w_grouped["weather_soil_moisture_0_7cm"].agg(
        weather_soil_moisture_0_7cm_mean="mean",
        weather_soil_moisture_0_7cm_min="min",
        weather_soil_moisture_0_7cm_max="max",
    )
    sm2_stats = w_grouped["weather_soil_moisture_7_28cm"].agg(
        weather_soil_moisture_7_28cm_mean="mean",
        weather_soil_moisture_7_28cm_min="min",
        weather_soil_moisture_7_28cm_max="max",
    )
    sm3_stats = w_grouped["weather_soil_moisture_28_100cm"].agg(
        weather_soil_moisture_28_100cm_mean="mean",
        weather_soil_moisture_28_100cm_min="min",
        weather_soil_moisture_28_100cm_max="max",
    )

    et0_stats = w_grouped["weather_evapotranspiration_et0"].agg(
        weather_evapotranspiration_et0_sum="sum",
        weather_evapotranspiration_et0_mean="mean",
    )
    wb_stats = w_grouped["weather_water_balance"].agg(
        weather_water_balance_sum="sum",
        weather_water_balance_mean="mean",
    )

    crop_time_stats = (
        w_grouped[["crop_age_days", "days_to_harvest", "season_progress_ratio"]].mean().round(2)
    )

    monthly_w = pd.concat(
        [
            w_meta,
            crop_time_stats,
            temp_stats,
            app_temp_stats,
            precip_stats,
            rain_stats,
            rainy_days,
            solar_stats,
            wind_stats,
            soil_temp_stats,
            sm1_stats,
            sm2_stats,
            sm3_stats,
            et0_stats,
            wb_stats,
        ],
        axis=1,
    ).reset_index()

    # Sentinel-2 oylik agregatsiya
    s2_grouped = df_s2.groupby("year_month")
    s2_parts = []
    s2_indices = [
        "s2_ndvi",
        "s2_evi",
        "s2_gndvi",
        "s2_savi",
        "s2_msavi",
        "s2_osavi",
        "s2_ndre",
        "s2_ci_red_edge",
        "s2_ndwi",
        "s2_ndmi",
    ]
    for idx in s2_indices:
        if idx in df_s2.columns:
            idx_df = s2_grouped[idx].agg(mean="mean", max="max", min="min", std="std").rename(
                columns={
                    "mean": f"{idx}_mean",
                    "max": f"{idx}_max",
                    "min": f"{idx}_min",
                    "std": f"{idx}_std",
                }
            )
            s2_parts.append(idx_df)

    s2_bands = [
        "s2_b02_blue",
        "s2_b03_green",
        "s2_b04_red",
        "s2_b05_red_edge_1",
        "s2_b06_red_edge_2",
        "s2_b07_red_edge_3",
        "s2_b08_nir",
        "s2_b8a_nir_narrow",
        "s2_b11_swir_1",
        "s2_b12_swir_2",
    ]
    for b in s2_bands:
        if b in df_s2.columns:
            b_df = s2_grouped[b].agg(mean="mean", max="max", min="min").rename(
                columns={"mean": f"{b}_mean", "max": f"{b}_max", "min": f"{b}_min"}
            )
            s2_parts.append(b_df)

    if (
        "s2_cloud_percentage" in df_s2.columns
        and "s2_cloud_probability" in df_s2.columns
    ):
        quality_df = s2_grouped[
            ["s2_cloud_percentage", "s2_cloud_probability"]
        ].mean().rename(
            columns={
                "s2_cloud_percentage": "s2_cloud_percentage_mean",
                "s2_cloud_probability": "s2_cloud_probability_mean",
            }
        )
        s2_parts.append(quality_df)

    monthly_s2 = (
        pd.concat(s2_parts, axis=1).reset_index()
        if s2_parts
        else pd.DataFrame({"year_month": monthly_w["year_month"]})
    )

    # Sentinel-1 oylik agregatsiya
    s1_grouped = df_s1.groupby("year_month")
    s1_parts = []
    s1_vars = ["s1_vv", "s1_vh", "s1_vv_vh_ratio"]
    for sv in s1_vars:
        if sv in df_s1.columns:
            sv_df = s1_grouped[sv].agg(mean="mean", max="max", min="min").rename(
                columns={"mean": f"{sv}_mean", "max": f"{sv}_max", "min": f"{sv}_min"}
            )
            s1_parts.append(sv_df)
    monthly_s1 = (
        pd.concat(s1_parts, axis=1).reset_index()
        if s1_parts
        else pd.DataFrame({"year_month": monthly_w["year_month"]})
    )

    # Birlashtirish
    monthly_merged = pd.merge(monthly_w, monthly_s2, on="year_month", how="left")
    monthly_merged = pd.merge(monthly_merged, monthly_s1, on="year_month", how="left")
    monthly_merged = monthly_merged.sort_values(by="year_month").reset_index(drop=True)

    sat_cols = [c for c in monthly_merged.columns if c.startswith("s2_") or c.startswith("s1_")]
    monthly_merged[sat_cols] = (
        monthly_merged[sat_cols].interpolate(method="linear").ffill().bfill().fillna(0.0)
    )

    std_cols = [c for c in monthly_merged.columns if c.endswith("_std")]
    monthly_merged[std_cols] = monthly_merged[std_cols].fillna(0.0)

    # Defragment before column assignments
    df_features = monthly_merged.copy()
    years = df_features["year_month"].apply(lambda ym: int(ym.split("-")[0]))
    months = df_features["year_month"].apply(lambda ym: int(ym.split("-")[1]))
    df_features["year"] = years
    df_features["month"] = months

    if target_year in df_features["year"].values:
        df_features = df_features[df_features["year"] == target_year].copy()

    m_sin = np.sin(2 * np.pi * df_features["month"] / 12.0).round(4)
    m_cos = np.cos(2 * np.pi * df_features["month"] / 12.0).round(4)
    df_features = df_features.drop(columns=["year", "year_month", "month"]).copy()
    df_features["month_sin"] = m_sin
    df_features["month_cos"] = m_cos

    float_cols = df_features.select_dtypes(include=["float64", "float32"]).columns
    for col in float_cols:
        df_features[col] = df_features[col].round(2)

    return df_features.copy()


class YieldInferenceService:
    def __init__(self, models_dir: Path | str = Path("models")) -> None:
        self.models_dir = Path(models_dir)
        self._loaded_models: dict[str, Any] = {}
        self._feature_names: dict[str, list[str]] = {}

    def list_available_models(self) -> list[dict[str, str]]:
        """Mavjud joblib modellarini aniqlaydi."""
        model_files = sorted(glob.glob(str(self.models_dir / "*.joblib")))
        result = []
        for fpath in model_files:
            fname = os.path.basename(fpath)
            if "feature_names" in fname:
                continue
            crop = (
                "cotton"
                if fname.startswith("cotton")
                else ("wheat" if fname.startswith("wheat") else "general")
            )
            name = "CatBoost"
            if "LightGBM" in fname or "lgbm" in fname.lower():
                name = "LightGBM"
            elif "XGBoost" in fname or "xgboost" in fname.lower():
                name = "XGBoost"
            elif "RandomForest" in fname or "rf" in fname.lower():
                name = "RandomForest"
            elif "GradientBoosting" in fname:
                name = "GradientBoosting"

            display_name = f"{crop.capitalize()} - {name}"
            result.append(
                {
                    "name": name,
                    "crop": crop,
                    "file": fname,
                    "display_name": display_name,
                    "type": "Regression",
                }
            )
        return result

    def _load_model(self, crop: str, model_name: str) -> tuple[Any, list[str]]:
        cache_key = f"{crop}_{model_name.strip()}"
        if cache_key in self._loaded_models:
            return self._loaded_models[cache_key], self._feature_names.get(crop, [])

        pattern = str(self.models_dir / f"{crop}_{model_name.strip()}*.joblib")
        matching = sorted(glob.glob(pattern))
        if not matching:
            matching = sorted(glob.glob(str(self.models_dir / f"{crop}_*.joblib")))

        if not matching:
            raise FileNotFoundError(f"'{crop}' uchun '{model_name}' modeli topilmadi")

        selected_file = matching[-1]
        model_obj = joblib.load(selected_file)
        self._loaded_models[cache_key] = model_obj

        feat_path = self.models_dir / f"{crop}_feature_names.joblib"
        feats = joblib.load(feat_path) if feat_path.is_file() else []
        self._feature_names[crop] = feats
        return model_obj, feats

    def predict_yield(
        self,
        df_features: pd.DataFrame,
        crop: str = "cotton",
        model_name: str = "CatBoost",
    ) -> tuple[float, float, float, list[FeatureImportanceItem], str]:
        """ML modeli orqali 1 gektar hosilini hisoblaydi (t/ha)."""
        model, expected_features = self._load_model(crop, model_name)

        if expected_features:
            for f in expected_features:
                if f not in df_features.columns:
                    df_features[f] = 0.0
            X = df_features[expected_features].copy()
        else:
            X = df_features.copy()

        X = X.fillna(0.0).replace([np.inf, -np.inf], 0.0)
        preds = model.predict(X)

        raw_final_yield = float(np.mean(preds))
        final_yield = float(max(0.01, raw_final_yield))

        pred_std = float(np.std(preds)) if len(preds) > 1 else (final_yield * 0.15)
        margin = float(round(max(0.1, pred_std), 2))

        yield_min = float(round(max(0.01, final_yield - margin), 2))
        yield_max = float(round(final_yield + margin, 2))
        final_yield = float(round(final_yield, 2))

        top_features_list: list[FeatureImportanceItem] = []
        if hasattr(model, "feature_importances_") and len(expected_features) == len(
            model.feature_importances_
        ):
            importances = model.feature_importances_
            feat_imp_df = pd.DataFrame(
                {"feature": expected_features, "importance": importances}
            ).sort_values(by="importance", ascending=False).head(10)

            for _, row in feat_imp_df.iterrows():
                f_name = str(row["feature"])
                desc = FEATURE_DESCRIPTIONS.get(f_name, f_name)
                top_features_list.append(
                    FeatureImportanceItem(
                        feature=f_name,
                        importance=round(float(row["importance"]), 4),
                        description=desc,
                    )
                )
        else:
            std_vals = X.std()
            top_feats = std_vals.sort_values(ascending=False).head(10)
            total_std = float(top_feats.sum()) if top_feats.sum() > 0 else 1.0
            for f_name, val in top_feats.items():
                desc = FEATURE_DESCRIPTIONS.get(str(f_name), str(f_name))
                top_features_list.append(
                    FeatureImportanceItem(
                        feature=str(f_name),
                        importance=round(float(val / total_std), 4),
                        description=desc,
                    )
                )

        actual_model_name = type(model).__name__
        return final_yield, yield_min, yield_max, top_features_list, actual_model_name


def _safe_float(val: Any, default: float) -> float:
    if val is None:
        return default
    try:
        f = float(val)
        if np.isnan(f) or np.isinf(f):
            return default
        return float(round(f, 3))
    except (ValueError, TypeError):
        return default


def generate_phenology_timeline(
    df_s2: pd.DataFrame,
    df_s1: pd.DataFrame,
    df_w: pd.DataFrame,
) -> list[PhenologyDataPoint]:
    """Fenologiya va oylik dinamika grafigi nuqtalarini tuzadi."""
    s2_monthly = df_s2.groupby(df_s2["date"].dt.month).agg(
        ndvi=("s2_ndvi", "mean") if "s2_ndvi" in df_s2.columns else ("s2_b08_nir", "count"),
        evi=("s2_evi", "mean") if "s2_evi" in df_s2.columns else ("s2_b08_nir", "count"),
        ndre=("s2_ndre", "mean") if "s2_ndre" in df_s2.columns else ("s2_b08_nir", "count"),
        ndmi=("s2_ndmi", "mean") if "s2_ndmi" in df_s2.columns else ("s2_b08_nir", "count"),
    )
    s1_monthly = df_s1.groupby(df_s1["date"].dt.month).agg(
        vh=("s1_vh", "mean") if "s1_vh" in df_s1.columns else ("date", "count"),
        vv_vh=("s1_vv_vh_ratio", "mean") if "s1_vv_vh_ratio" in df_s1.columns else ("date", "count"),
    )
    w_monthly = df_w.groupby(df_w["date"].dt.month).agg(
        temp=("weather_temperature_2m", "mean")
        if "weather_temperature_2m" in df_w.columns
        else ("date", "count"),
        rain=("weather_total_precipitation", "sum")
        if "weather_total_precipitation" in df_w.columns
        else ("date", "count"),
        sm=("weather_soil_moisture_0_7cm", "mean")
        if "weather_soil_moisture_0_7cm" in df_w.columns
        else ("date", "count"),
    )

    all_months = sorted(list(set(s2_monthly.index).union(set(w_monthly.index))))
    if not all_months:
        all_months = [4, 5, 6, 7, 8, 9, 10]

    timeline: list[PhenologyDataPoint] = []
    for m in all_months:
        s2_ndvi_val = s2_monthly.loc[m, "ndvi"] if (m in s2_monthly.index and "ndvi" in s2_monthly.columns) else None
        s2_evi_val = s2_monthly.loc[m, "evi"] if (m in s2_monthly.index and "evi" in s2_monthly.columns) else None
        s2_ndre_val = s2_monthly.loc[m, "ndre"] if (m in s2_monthly.index and "ndre" in s2_monthly.columns) else None
        s2_ndmi_val = s2_monthly.loc[m, "ndmi"] if (m in s2_monthly.index and "ndmi" in s2_monthly.columns) else None
        s1_vh_val = s1_monthly.loc[m, "vh"] if (m in s1_monthly.index and "vh" in s1_monthly.columns) else None
        s1_vv_vh_val = s1_monthly.loc[m, "vv_vh"] if (m in s1_monthly.index and "vv_vh" in s1_monthly.columns) else None
        w_temp_val = w_monthly.loc[m, "temp"] if (m in w_monthly.index and "temp" in w_monthly.columns) else None
        w_rain_val = w_monthly.loc[m, "rain"] if (m in w_monthly.index and "rain" in w_monthly.columns) else None
        w_sm_val = w_monthly.loc[m, "sm"] if (m in w_monthly.index and "sm" in w_monthly.columns) else None

        timeline.append(
            PhenologyDataPoint(
                month=int(m),
                ndvi=_safe_float(s2_ndvi_val, 0.35),
                evi=_safe_float(s2_evi_val, 0.28),
                ndre=_safe_float(s2_ndre_val, 0.22),
                ndmi=_safe_float(s2_ndmi_val, 0.18),
                s1_vh=_safe_float(s1_vh_val, -15.5),
                s1_vv_vh=_safe_float(s1_vv_vh_val, 5.2),
                temp_mean=_safe_float(w_temp_val, 24.0),
                rain_sum=_safe_float(w_rain_val, 12.0),
                soil_moisture=_safe_float(w_sm_val, 0.22),
            )
        )
    return timeline

