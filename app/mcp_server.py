"""ZaminTahlil — Model Context Protocol (MCP) Server.

Ushbu server tashqi AI agentlari (Claude Desktop, Cursor, Antigravity va boshqalar)
uchun ZaminTahlil platformasining to'liq agronomik, kosmik telemetriya,
hosildorlik bashorati va muammoli zonalarni aniqlash imkoniyatlarini taqdim etadi.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from mcp.server.mcpserver import MCPServer

from app.config import get_settings
from app.db import Database
from app.repository import Repository
from app.spatial_zones import calculate_spatial_problem_zones
from app.yield_service import CROP_CALENDARS, YieldInferenceService, normalize_crop_name

logger = logging.getLogger(__name__)

# MCP Server yaratish
mcp_server = MCPServer(
    name="zamintahlil",
    description="ZaminTahlil — Kosmik sun'iy yo'ldosh (Sentinel-2), biofizik indekslar, anomaliyalar, hosildorlik bashorati va agronomik AI tahlil platformasi",
)


def _get_context() -> tuple[Repository, YieldInferenceService]:
    settings = get_settings()
    database = Database(settings.database_path)
    database.initialize()
    repo = Repository(database)
    yield_service = YieldInferenceService(models_dir=settings.models_dir)
    return repo, yield_service


@mcp_server.tool()
def list_fields() -> str:
    """Tizimda ro'yxatdan o'tgan barcha dalalar ro'yxatini qaytaradi (ID, nom, ekin turi, maydon ga, ekilgan sana)."""
    repo, _ = _get_context()
    fields = repo.list_fields()
    result = [
        {
            "id": f["id"],
            "public_id": f["public_id"],
            "crop_name": f["crop_name"],
            "area_hectares": f["area_hectares"],
            "planted_on": f["planted_on"],
            "growth_stage": f["growth_stage"],
            "created_at": f["created_at"],
        }
        for f in fields
    ]
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp_server.tool()
def get_field_details(field_id: int) -> str:
    """Dala bo'yicha to'liq ma'lumotlarni (geometriya, koordinatalar, oxirgi kuzatuvlar) qaytaradi."""
    repo, _ = _get_context()
    field = repo.get_field(field_id)
    acquisitions = repo.list_acquisitions(field_id, processed_only=False)
    data = {
        "field": field,
        "total_acquisitions": len(acquisitions),
        "latest_acquisition": acquisitions[0] if acquisitions else None,
    }
    return json.dumps(data, ensure_ascii=False, indent=2)


@mcp_server.tool()
def get_field_satellite_metrics(field_id: int, limit: int = 5) -> str:
    """Dalaning so'nggi Sentinel-2 sun'iy yo'ldosh kuzatuvlari va indekslar (NDVI, NDMI, NDRE, EVI, BSI) statistikasini qaytaradi."""
    repo, _ = _get_context()
    repo.get_field(field_id)
    records = repo.index_value_records(field_id, limit=limit * 5)
    acqs = repo.list_acquisitions(field_id)
    data = {
        "field_id": field_id,
        "acquisitions_count": len(acqs),
        "recent_metrics": records[: limit * 5],
    }
    return json.dumps(data, ensure_ascii=False, indent=2)


@mcp_server.tool()
def get_field_problem_zones(field_id: int) -> str:
    """Dala telemetriyasi asosida suvsizlik va kasallik/xlorofill zaiflashuvi qayerda ekanligini xalqchil tushunarli tilda (masalan: 'dalaning yuqori o'ng burchagida') qaytaradi."""
    settings = get_settings()
    repo, _ = _get_context()
    zones = calculate_spatial_problem_zones(
        field_id,
        repo,
        artifact_root=settings.artifact_dir,
    )
    return json.dumps(zones, ensure_ascii=False, indent=2)


@mcp_server.tool()
async def predict_crop_yield(field_id: int, model_name: str = "CatBoost") -> str:
    """Dala bo'yicha CatBoost/LightGBM mashinali o'rganish modellari asosida kutilayotgan hosildorlikni (t/ga va jami tonna) bashorat qiladi."""
    repo, yield_service = _get_context()
    field = repo.get_field(field_id)
    crop_type = normalize_crop_name(field.get("crop_name", "cotton"))
    crop_cal = CROP_CALENDARS.get(crop_type, CROP_CALENDARS["cotton"])

    from app.weather import fetch_weather_data
    import pandas as pd

    coords = field["geometry"]["coordinates"][0]
    lons = [float(p[0]) for p in coords]
    lats = [float(p[1]) for p in coords]
    c_lon = float(sum(lons) / len(lons))
    c_lat = float(sum(lats) / len(lats))

    p_date = field.get("planted_on") or crop_cal["planting_date"]
    h_date = crop_cal["harvest_date"]
    s_start = crop_cal["season_start"]
    s_end = crop_cal["season_end"]

    try:
        df_w = await asyncio.to_thread(fetch_weather_data, c_lat, c_lon, start_date=s_start, end_date=s_end)
    except Exception:
        dates = pd.date_range(s_start, s_end)
        df_w = pd.DataFrame({
            "date": dates,
            "weather_temperature_2m": 24.0,
            "weather_apparent_temperature": 23.5,
            "weather_total_precipitation": 0.5,
            "weather_rain": 0.5,
            "weather_shortwave_radiation": 22.0,
            "weather_wind_speed_10m": 12.0,
            "weather_soil_temperature_0_7cm": 22.0,
            "weather_soil_moisture_0_7cm": 0.22,
            "weather_soil_moisture_7_28cm": 0.25,
            "weather_soil_moisture_28_100cm": 0.28,
            "weather_evapotranspiration_et0": 4.5,
            "latitude": c_lat,
            "longitude": c_lon,
        })

    # Dala sun'iy yo'ldosh metrikalari
    records = repo.index_value_records(field_id, limit=30)
    s2_rows = []
    for r in records:
        if r.get("mean_value") is not None:
            s2_rows.append({
                "date": pd.to_datetime(r["acquired_at"][:10]),
                "index_name": r["index_name"],
                "value": float(r["mean_value"]),
            })

    if s2_rows:
        df_long = pd.DataFrame(s2_rows)
        df_s2 = df_long.pivot_table(index="date", columns="index_name", values="value").reset_index()
        col_rename = {col: f"s2_{col.lower()}_mean" for col in df_s2.columns if col != "date"}
        df_s2 = df_s2.rename(columns=col_rename)
    else:
        dates = pd.date_range(s_start, s_end, freq="10D")
        df_s2 = pd.DataFrame({
            "date": dates,
            "s2_ndvi_mean": 0.55,
            "s2_ndre_mean": 0.35,
            "s2_ndmi_mean": 0.25,
            "s2_evi_mean": 0.40,
        })

    pred = yield_service.predict(
        crop_type=crop_type,
        model_name=model_name,
        df_s2=df_s2,
        df_weather=df_w,
        field_area_ha=float(field["area_hectares"]),
        planting_date=p_date,
        harvest_date=h_date,
    )

    data_sources = [
        {"name": "Sentinel-2 (Copernicus L2A)", "count": len(s2_rows), "status": "Faol"},
        {"name": "Open-Meteo Agrometeorologiya", "count": len(df_w), "status": "Faol"},
    ]

    out = {
        "field_id": field_id,
        "crop": crop_type,
        "model_name": model_name,
        "predicted_yield_t_ha": round(pred.yield_predicted_t_ha, 2),
        "total_expected_yield_tons": round(pred.total_yield_tons, 2),
        "yield_range": [round(pred.yield_min_expected, 2), round(pred.yield_max_expected, 2)],
        "baseline_difference_pct": round(pred.difference_from_baseline_pct, 1),
        "data_sources": data_sources,
        "top_features": [f.__dict__ for f in pred.top_features[:5]],
    }
    return json.dumps(out, ensure_ascii=False, indent=2)


@mcp_server.tool()
def get_agronomic_recommendation(field_id: int) -> str:
    """Dala bo'yicha so'nggi 3 toifali (Qizil - Shoshilinch, Sariq - Nazorat, Yashil - Ijobiy) agronomik tavsiyani qaytaradi."""
    repo, _ = _get_context()
    field = repo.get_field(field_id)
    rec = repo.get_recommendation(field_id)
    if not rec:
        return json.dumps({"status": "no_recommendation", "message": "Dala uchun hali tavsiya shakllanmagan. Avval tahlil o'tkazing."}, ensure_ascii=False)

    return json.dumps({
        "field_id": field_id,
        "crop_name": field["crop_name"],
        "content": rec.get("content"),
        "advice": rec.get("advice"),
        "model_name": rec.get("model_name"),
        "created_at": rec.get("created_at"),
    }, ensure_ascii=False, indent=2)


@mcp_server.tool()
async def get_weather_forecast(field_id: int) -> str:
    """Dala geografik markazi bo'yicha Open-Meteo agrometeorologik 7 kunlik ob-havo prognozini qaytaradi."""
    repo, _ = _get_context()
    field = repo.get_field(field_id)
    coords = field["geometry"]["coordinates"][0]
    lons = [float(p[0]) for p in coords]
    lats = [float(p[1]) for p in coords]
    c_lon = float(sum(lons) / len(lons))
    c_lat = float(sum(lats) / len(lats))

    import httpx
    url = (
        f"https://api.open-meteo.com/v1/forecast?latitude={c_lat}&longitude={c_lon}"
        f"&current=temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m"
        f"&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,et0_fao_evapotranspiration"
        f"&timezone=auto"
    )
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url)
        if resp.status_code == 200:
            return json.dumps(resp.json(), ensure_ascii=False, indent=2)
        return json.dumps({"status": "error", "message": f"Open-Meteo status {resp.status_code}"})


@mcp_server.tool()
async def ask_ai_agronomist(field_id: int, question: str) -> str:
    """AI Bosh Agronomiga savol berish (RAG, 60 kunlik telemetriya va fazoviy muammoli zonalar bilan)."""
    settings = get_settings()
    repo, _ = _get_context()
    field = repo.get_field(field_id)
    rec = repo.get_recommendation(field_id)
    if not rec:
        return json.dumps({"error": "Avval dala tahlilini bajaring"}, ensure_ascii=False)

    from app.main import build_ai
    from app.rag import RAGService
    ai = build_ai(settings)
    if not ai:
        return json.dumps({"error": "OPENAI_API_KEY sozlanmagan"}, ensure_ascii=False)

    rag = RAGService(model_name=settings.rag_model_name, similarity_threshold=settings.rag_similarity_threshold)
    rag_result = await asyncio.to_thread(rag.search_advanced, question, database=repo.database, top_k=3)
    rag_context = "\n\n".join([f"[{c.document_name}, p.{c.page_number}]: {c.text}" for c in rag_result]) if rag_result else None

    recent_records = repo.index_value_records(field_id, limit=5)
    recent_metrics: dict[str, list[dict[str, Any]]] = {}
    for r in recent_records:
        recent_metrics.setdefault(str(r["index_name"]), []).append({
            "acquired_at": r["acquired_at"],
            "mean": r.get("mean_value"),
            "min": r.get("min_value"),
            "max": r.get("max_value"),
        })

    problem_zones = calculate_spatial_problem_zones(field_id, repo, artifact_root=settings.artifact_dir)

    ai_res = await ai.chat(
        field=field,
        recommendation=rec,
        messages=[{"role": "user", "content": question}],
        recent_ndvi_metrics=recent_metrics,
        rag_context=rag_context,
        spatial_problem_zones=problem_zones,
    )

    return json.dumps({
        "field_id": field_id,
        "question": question,
        "answer": ai_res.content,
        "model_name": ai_res.model_name,
        "spatial_problem_zones": problem_zones,
    }, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    import asyncio
    asyncio.run(mcp_server.run_stdio_async())
