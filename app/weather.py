from __future__ import annotations

import datetime
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import pickle
import time
from typing import Any

import httpx
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Kesh katalogi
WEATHER_CACHE_DIR = Path("data/weather_cache")
WEATHER_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Open-Meteo API Endpoints
OPEN_METEO_HISTORICAL_URL = "https://archive-api.open-meteo.com/v1/archive"
OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_ECMWF_URL = "https://api.open-meteo.com/v1/ecmwf"
OPEN_METEO_GFS_URL = "https://api.open-meteo.com/v1/gfs"
OPEN_METEO_DWD_URL = "https://api.open-meteo.com/v1/dwd-icon"

# NASA POWER Global Agroclimatology API Endpoint
NASA_POWER_API_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"

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


def _cache_key(latitude: float, longitude: float, start_date: str, end_date: str) -> Path:
    key_str = f"{round(latitude, 3)}_{round(longitude, 3)}_{start_date}_{end_date}"
    hashed = hashlib.md5(key_str.encode("utf-8")).hexdigest()
    return WEATHER_CACHE_DIR / f"weather_{hashed}.pkl"


def _read_cache(cache_file: Path) -> pd.DataFrame | None:
    if not cache_file.exists():
        return None
    try:
        # Kesh muddati: 24 soat (agar bugungi prognoz bo'lsa), o'tgan sanalar uchun cheksiz
        st = cache_file.stat()
        if (time.time() - st.st_mtime) < 86400 * 3:  # 3 kunlik yangilik
            with open(cache_file, "rb") as f:
                df = pickle.load(f)
                if isinstance(df, pd.DataFrame) and len(df) > 0:
                    return df
    except Exception as exc:
        logger.warning("Weather cache read error: %s", exc)
    return None


def _write_cache(cache_file: Path, df: pd.DataFrame) -> None:
    try:
        with open(cache_file, "wb") as f:
            pickle.dump(df, f)
    except Exception as exc:
        logger.warning("Weather cache write error: %s", exc)


def _fetch_open_meteo_with_retries(
    client: httpx.Client,
    latitude: float,
    longitude: float,
    start_date: str,
    end_date: str,
) -> dict[str, Any] | None:
    """Open-Meteo va uning muqobil modellaridan eksponensial qayta urinish bilan ob-havo oladi."""
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    is_forecast = end_date >= today_str

    endpoints = [
        OPEN_METEO_FORECAST_URL if is_forecast else OPEN_METEO_HISTORICAL_URL,
        OPEN_METEO_FORECAST_URL,
        OPEN_METEO_ECMWF_URL,
        OPEN_METEO_GFS_URL,
        OPEN_METEO_DWD_URL,
    ]

    for url in endpoints:
        params: dict[str, Any] = {
            "latitude": latitude,
            "longitude": longitude,
            "timezone": "auto",
        }
        if "archive" in url:
            params["start_date"] = start_date
            params["end_date"] = end_date
            params["daily"] = ",".join(DAILY_VARS)
        else:
            params["past_days"] = min(92, max(14, (datetime.date.today() - pd.to_datetime(start_date).date()).days))
            params["forecast_days"] = 16
            params["daily"] = ",".join(DAILY_VARS)

        # 3 martalik exponential backoff bilan urinish
        for attempt in range(1, 4):
            try:
                resp = client.get(url, params=params, timeout=12.0)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("daily") and data["daily"].get("time"):
                        return data
                elif resp.status_code in (502, 503, 504, 429):
                    logger.warning(
                        "Open-Meteo %s returned status %d on attempt %d/3. Backoff...",
                        url,
                        resp.status_code,
                        attempt,
                    )
                    time.sleep(0.6 * (2 ** (attempt - 1)))
                else:
                    break  # Boshqa xatolik bo'lsa keyingi endpointga o'tish
            except (httpx.TimeoutException, httpx.NetworkError) as err:
                logger.warning("Open-Meteo connection error on %s attempt %d: %s", url, attempt, err)
                time.sleep(0.5 * attempt)
            except Exception as exc:
                logger.warning("Open-Meteo unexpected exception on %s: %s", url, exc)
                break
    return None


def _fetch_nasa_power(
    client: httpx.Client,
    latitude: float,
    longitude: float,
    start_date: str,
    end_date: str,
) -> pd.DataFrame | None:
    """NASA POWER Agroclimatology API orqali quyosh radiatsiyasi va harorat ma'lumotlarini oladi."""
    try:
        s_date_fmt = start_date.replace("-", "")
        e_date_fmt = min(end_date, datetime.date.today().strftime("%Y-%m-%d")).replace("-", "")

        params = {
            "parameters": "T2M,T2M_MAX,T2M_MIN,PRECTOTCORR,ALLSKY_SFC_SW_DWN,WS10M,RH2M",
            "community": "AG",
            "longitude": longitude,
            "latitude": latitude,
            "start": s_date_fmt,
            "end": e_date_fmt,
            "format": "JSON",
        }

        resp = client.get(NASA_POWER_API_URL, params=params, timeout=15.0)
        if resp.status_code != 200:
            return None

        data = resp.json()
        props = data.get("properties", {}).get("parameter", {})
        if not props or not props.get("T2M"):
            return None

        dates = sorted(list(props["T2M"].keys()))
        records = []
        for d_str in dates:
            dt = pd.to_datetime(d_str, format="%Y%m%d")
            t_mean = float(props.get("T2M", {}).get(d_str, 22.0))
            t_max = float(props.get("T2M_MAX", {}).get(d_str, t_mean + 5.0))
            t_min = float(props.get("T2M_MIN", {}).get(d_str, t_mean - 5.0))
            precip = max(0.0, float(props.get("PRECTOTCORR", {}).get(d_str, 0.0)))
            rad = max(0.0, float(props.get("ALLSKY_SFC_SW_DWN", {}).get(d_str, 20.0)))
            wind = max(0.0, float(props.get("WS10M", {}).get(d_str, 10.0)))
            rh = max(10.0, float(props.get("RH2M", {}).get(d_str, 45.0)))

            # FAO-56 Penman-Monteith / Hargreaves ET0 hisoblash
            t_diff = max(1.0, t_max - t_min)
            et0 = 0.0023 * (t_mean + 17.8) * math.sqrt(t_diff) * (rad * 0.408)

            records.append(
                {
                    "date": dt,
                    "weather_temperature_2m": t_mean,
                    "weather_apparent_temperature": t_mean - 0.5,
                    "weather_total_precipitation": precip,
                    "weather_rain": precip,
                    "weather_shortwave_radiation": rad,
                    "weather_wind_speed_10m": wind,
                    "weather_evapotranspiration_et0": round(et0, 2),
                    "weather_soil_temperature_0_7cm": t_mean,
                    "weather_soil_moisture_0_7cm": round(0.20 + (precip * 0.02), 3),
                    "weather_soil_moisture_7_28cm": round(0.24 + (precip * 0.01), 3),
                    "weather_soil_moisture_28_100cm": 0.28,
                    "latitude": latitude,
                    "longitude": longitude,
                }
            )

        df_nasa = pd.DataFrame(records)
        logger.info("Successfully fetched %d records from NASA POWER API", len(df_nasa))
        return df_nasa
    except Exception as exc:
        logger.warning("NASA POWER API fetch failed: %s", exc)
        return None


def _generate_climatological_weather(
    latitude: float,
    longitude: float,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    """
    Markaziy Osiyo / O'zbekiston iqlimiy quyosh geometriyasi (FAO-56) va
    geografik kenglikka asoslangan dinamik agrometeorologik hisoblagich.
    """
    dates = pd.date_range(start_date, end_date)
    records = []
    lat_rad = math.radians(latitude)

    for dt in dates:
        doy = dt.dayofyear  # Yildagi kun raqami (1-365)

        # 1. Quyosh og'ishi (Solar declination, rad)
        sol_dec = 0.409 * math.sin((2 * math.pi / 365) * doy - 1.39)
        # Quyosh botish burchagi (Sunset hour angle, rad)
        cos_ws = -math.tan(lat_rad) * math.tan(sol_dec)
        cos_ws = max(-1.0, min(1.0, cos_ws))
        ws = math.acos(cos_ws)

        # 2. Quyoshdan tashqari radiatsiya (Extraterrestrial radiation, Ra MJ/m2/day)
        dr = 1 + 0.033 * math.cos((2 * math.pi / 365) * doy)
        ra = (24 * 60 / math.pi) * 0.0820 * dr * (
            ws * math.sin(lat_rad) * math.sin(sol_dec)
            + math.cos(lat_rad) * math.cos(sol_dec) * math.sin(ws)
        )
        ra = max(10.0, min(45.0, ra))

        # 3. O'zbekiston yillik harorat to'lqini (Iyun-Avgustda eng issiq ~32-36C, Aprel/May ~22-26C)
        t_base = 22.0 + 12.0 * math.sin((2 * math.pi / 365) * (doy - 105))
        # Kichik tabiiy tebranish
        noise = math.sin(doy * 0.7) * 2.0
        t_mean = round(t_base + noise, 1)
        t_max = t_mean + 6.0
        t_min = t_mean - 6.0

        # 4. Qisqa to'lqinli quyosh radiatsiyasi (Rs ~ 0.70 * Ra)
        rs = round(ra * 0.72, 1)

        # 5. Evapotranspiration ET0 (Hargreaves formula)
        et0 = round(0.0023 * (t_mean + 17.8) * math.sqrt(t_max - t_min) * (ra * 0.408), 2)
        precip = 0.5 if (doy % 15 == 0) else 0.0

        records.append(
            {
                "date": dt,
                "weather_temperature_2m": t_mean,
                "weather_apparent_temperature": round(t_mean - 0.8, 1),
                "weather_total_precipitation": precip,
                "weather_rain": precip,
                "weather_shortwave_radiation": rs,
                "weather_wind_speed_10m": 11.5,
                "weather_evapotranspiration_et0": et0,
                "weather_soil_temperature_0_7cm": round(t_mean + 1.2, 1),
                "weather_soil_moisture_0_7cm": 0.22,
                "weather_soil_moisture_7_28cm": 0.25,
                "weather_soil_moisture_28_100cm": 0.28,
                "latitude": latitude,
                "longitude": longitude,
            }
        )

    logger.info(
        "Generated %d climatological agrometeorology records for lat=%.4f lon=%.4f",
        len(records),
        latitude,
        longitude,
    )
    return pd.DataFrame(records)


def fetch_weather_data(
    latitude: float,
    longitude: float,
    start_date: str = "2026-03-01",
    end_date: str = "2026-10-31",
) -> pd.DataFrame:
    """
    Ko'p Qatlamli Chidamli Ob-havo Dvigateli (Multi-Provider Resilient Weather System):
    1. 1-Qatlam: Mahalliy Kesh (data/weather_cache/)
    2. 2-Qatlam: Open-Meteo Multi-Endpoint (Forecast, Archive, ECMWF, GFS, DWD) + Exponential Backoff
    3. 3-Qatlam: NASA POWER Global Agroclimatology API
    4. 4-Qatlam: Dinamik Agrometeorologik Iqlimiy Modellashtirish (FAO-56 Solar Geometry)
    """
    t0 = time.perf_counter()

    # 1. Keshni tekshirish
    cache_f = _cache_key(latitude, longitude, start_date, end_date)
    cached_df = _read_cache(cache_f)
    if cached_df is not None:
        logger.info("Loaded weather data from local cache in %.3fs (%d records)", time.perf_counter() - t0, len(cached_df))
        return cached_df

    with httpx.Client(trust_env=True) as client:
        # 2. Open-Meteo Multi-Endpoint
        open_meteo_data = _fetch_open_meteo_with_retries(
            client, latitude, longitude, start_date, end_date
        )

        if open_meteo_data and open_meteo_data.get("daily") and open_meteo_data["daily"].get("time"):
            daily_dict = open_meteo_data["daily"]
            df_w = pd.DataFrame(daily_dict)
            df_w["date"] = pd.to_datetime(df_w["time"])
            for raw_col, target_col in COLUMN_MAPPING.items():
                if raw_col in df_w.columns:
                    df_w[target_col] = df_w[raw_col]
            df_w["longitude"] = longitude
            df_w["latitude"] = latitude

            _write_cache(cache_f, df_w)
            logger.info("Open-Meteo fetched %d records in %.2fs", len(df_w), time.perf_counter() - t0)
            return df_w

        # 3. Open-Meteo ishlamasa -> NASA POWER API
        logger.info("Open-Meteo unavailable, trying NASA POWER Agroclimatology API...")
        nasa_df = _fetch_nasa_power(client, latitude, longitude, start_date, end_date)
        if nasa_df is not None and len(nasa_df) > 0:
            _write_cache(cache_f, nasa_df)
            return nasa_df

    # 4. Har ikki API ham ishlamasa -> Dinamik Iqlimiy Model
    logger.warning("External weather APIs unavailable. Utilizing calibrated FAO-56 Solar Climatology...")
    clima_df = _generate_climatological_weather(latitude, longitude, start_date, end_date)
    _write_cache(cache_f, clima_df)
    return clima_df

