import datetime
import logging
import time
from typing import Any

import httpx
import pandas as pd

logger = logging.getLogger(__name__)

OPEN_METEO_HISTORICAL_URL = "https://archive-api.open-meteo.com/v1/archive"
OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

DAILY_VARS: tuple[str, ...] = (
    "temperature_2m_max",
    "temperature_2m_min",
    "temperature_2m_mean",
    "apparent_temperature_max",
    "apparent_temperature_min",
    "apparent_temperature_mean",
    "precipitation_sum",
    "rain_sum",
    "shortwave_radiation_sum",
    "wind_speed_10m_max",
    "et0_fao_evapotranspiration",
    "soil_temperature_0_to_7cm_mean",
    "soil_moisture_0_to_7cm_mean",
    "soil_moisture_7_to_28cm_mean",
    "soil_moisture_28_to_100cm_mean",
)

COLUMN_MAPPING: dict[str, str] = {
    "temperature_2m_mean": "weather_temperature_2m",
    "apparent_temperature_mean": "weather_apparent_temperature",
    "precipitation_sum": "weather_total_precipitation",
    "rain_sum": "weather_rain",
    "shortwave_radiation_sum": "weather_shortwave_radiation",
    "wind_speed_10m_max": "weather_wind_speed_10m",
    "et0_fao_evapotranspiration": "weather_evapotranspiration_et0",
    "soil_temperature_0_to_7cm_mean": "weather_soil_temperature_0_7cm",
    "soil_moisture_0_to_7cm_mean": "weather_soil_moisture_0_7cm",
    "soil_moisture_7_to_28cm_mean": "weather_soil_moisture_7_28cm",
    "soil_moisture_28_to_100cm_mean": "weather_soil_moisture_28_100cm",
}


def fetch_weather_data(
    latitude: float,
    longitude: float,
    start_date: str = "2026-03-01",
    end_date: str = "2026-10-31",
) -> pd.DataFrame:
    """Open-Meteo Global Agrometeorology API orqali real kunlik ob-havo ma'lumotlarini yuklaydi."""
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    api_url = OPEN_METEO_HISTORICAL_URL if end_date < today_str else OPEN_METEO_FORECAST_URL

    params: dict[str, Any] = {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": start_date,
        "end_date": end_date,
        "daily": ",".join(DAILY_VARS),
        "timezone": "auto",
    }

    t0 = time.perf_counter()
    with httpx.Client(timeout=20.0, trust_env=True) as client:
        try:
            resp = client.get(api_url, params=params)
            if resp.status_code != 200:
                logger.warning("Weather API status=%d url=%s, falling back to forecast endpoint", resp.status_code, api_url)
                resp = client.get(
                    OPEN_METEO_FORECAST_URL,
                    params={
                        "latitude": latitude,
                        "longitude": longitude,
                        "daily": ",".join(DAILY_VARS),
                        "past_days": 92,
                        "forecast_days": 16,
                        "timezone": "auto",
                    },
                )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.error("Open-Meteo weather request failed: %s", exc)
            raise RuntimeError(f"Open-Meteo ob-havo xizmatiga ulanib bo'lmadi: {exc}") from exc

    daily_dict = data.get("daily")
    if not daily_dict or not daily_dict.get("time"):
        raise RuntimeError("Open-Meteo API dan bo'sh kunlik ma'lumot qaytdi")

    df_w = pd.DataFrame(daily_dict)
    df_w["date"] = pd.to_datetime(df_w["time"])

    for raw_col, target_col in COLUMN_MAPPING.items():
        if raw_col in df_w.columns:
            df_w[target_col] = df_w[raw_col]

    df_w["longitude"] = longitude
    df_w["latitude"] = latitude

    elapsed = time.perf_counter() - t0
    logger.info(
        "Weather data fetched in %.2fs records=%d lat=%.4f lon=%.4f",
        elapsed,
        len(df_w),
        latitude,
        longitude,
    )
    return df_w
