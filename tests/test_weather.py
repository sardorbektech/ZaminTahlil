from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pandas as pd
import pytest

from app.weather import (
    COLUMN_MAPPING,
    _cache_key,
    _generate_climatological_weather,
    _read_cache,
    _write_cache,
    fetch_weather_data,
)


def test_climatological_weather_generation() -> None:
    lat = 41.1555
    lon = 69.3141
    start_date = '2026-04-01'
    end_date = '2026-09-30'

    df = _generate_climatological_weather(lat, lon, start_date, end_date)
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 183

    expected_cols = [
        'date',
        'weather_temperature_2m',
        'weather_apparent_temperature',
        'weather_total_precipitation',
        'weather_shortwave_radiation',
        'weather_wind_speed_10m',
        'weather_evapotranspiration_et0',
        'weather_soil_temperature_0_7cm',
        'weather_soil_moisture_0_7cm',
        'weather_soil_moisture_7_28cm',
        'weather_soil_moisture_28_100cm',
        'latitude',
        'longitude',
    ]
    for col in expected_cols:
        assert col in df.columns, f'Missing column {col}'

    assert (df['weather_temperature_2m'] >= 10.0).all()
    assert (df['weather_temperature_2m'] <= 45.0).all()
    assert (df['weather_shortwave_radiation'] >= 10.0).all()
    assert (df['weather_evapotranspiration_et0'] >= 1.0).all()


def test_weather_caching(tmp_path: Path) -> None:
    lat = 40.5
    lon = 68.5
    cache_file = tmp_path / 'test_weather_cache.pkl'

    df_sample = pd.DataFrame(
        {
            'date': pd.date_range('2026-05-01', '2026-05-05'),
            'weather_temperature_2m': [25.0, 26.0, 27.0, 26.5, 25.5],
            'latitude': [lat] * 5,
            'longitude': [lon] * 5,
        }
    )

    _write_cache(cache_file, df_sample)
    assert cache_file.exists()

    cached = _read_cache(cache_file)
    assert cached is not None
    assert len(cached) == 5
    assert (cached['weather_temperature_2m'] == df_sample['weather_temperature_2m']).all()


def test_fetch_weather_data_handles_503_gracefully() -> None:
    lat = 41.1555
    lon = 69.3141
    start_date = '2026-06-01'
    end_date = '2026-06-10'

    mock_resp = MagicMock()
    mock_resp.status_code = 503

    with patch('httpx.Client.get', return_value=mock_resp):
        df = fetch_weather_data(lat, lon, start_date=start_date, end_date=end_date)
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 10
        assert 'weather_temperature_2m' in df.columns
        assert (df['weather_temperature_2m'] > 0).all()
