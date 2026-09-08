from __future__ import annotations

from datetime import date
import logging
from typing import Annotated, Any, cast

import numpy as np
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse

from app.analysis import AnalysisError, AnalysisService, generate_expert_agronomy_advice
from app.config import Settings
from app.constants import IMPORTANT_INDEXES, LAYER_NAMES
from app.deps import (
    ArtifactWriterDependency,
    RepositoryDependency,
    detail,
)
from app.rendering import ArtifactWriter, calculate_hotspot_coordinates
from app.repository import NotFoundError, Repository
from app.schemas import (
    AcquisitionOut,
    AnalyzeRequest,
    AnalyzeResponse,
    AnnualSeries,
    ArtifactOut,
    HistoricalMetricsRequest,
    HistoricalMetricsResponse,
    HistoricalSeries,
    RecommendationOut,
)
from app.sentinel import SentinelAuthError, SentinelError, SentinelHubClient

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Analysis"])


def serialize_acquisition(repository: Repository, value: dict[str, Any]) -> dict[str, Any]:
    return dict(value)


def _point_mean(record: dict[str, Any], writer: ArtifactWriter) -> float | None:
    if record["mean_value"] is not None or int(record["valid_pixel_count"]) == 0:
        mean = record["mean_value"]
        return float(mean) if mean is not None else None
    try:
        values = writer.read_values(str(record["relative_path"]))
    except FileNotFoundError:
        return None
    finite = np.clip(values[np.isfinite(values)], -1, 1)
    return float(np.average(finite)) if finite.size else None


def metric_points(
    field_id: int,
    repository: Repository,
    writer: ArtifactWriter,
    *,
    year: int | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
) -> list[dict[str, Any]]:
    grouped: dict[int, dict[str, Any]] = {}
    for record in repository.index_value_records(
        field_id, year=year, from_date=from_date, to_date=to_date, limit=None
    ):
        acquisition_id = int(record["acquisition_id"])
        point = grouped.setdefault(
            acquisition_id,
            {
                "acquisition_id": acquisition_id,
                "acquired_at": record["acquired_at"],
                "cloud_coverage": record["cloud_coverage"],
                "fully_cloudy": bool(record["fully_cloudy"]),
                "values": {name: None for name in IMPORTANT_INDEXES},
            },
        )
        point["values"][str(record["index_name"])] = _point_mean(record, writer)
    return list(grouped.values())


@router.post("/api/fields/{field_id}/analyze", response_model=AnalyzeResponse)
async def analyze(
    field_id: int,
    payload: AnalyzeRequest,
    request: Request,
    repository: RepositoryDependency,
) -> dict[str, object]:
    req_settings: Settings = request.app.state.settings
    sentinel = cast(SentinelHubClient | None, request.app.state.sentinel)
    if sentinel is None:
        raise HTTPException(
            status_code=503,
            detail="Sentinel Hub (Copernicus) credentials sozlanmagan. Iltimos, .env faylida SENTINEL_HUB_CLIENT_ID va SENTINEL_HUB_CLIENT_SECRET ni kiriting.",
        )
    service = AnalysisService(
        repository,
        sentinel,
        request.app.state.artifact_writer,
        request.app.state.ai,
        req_settings.cloud_free_threshold,
    )
    try:
        result = await service.analyze(field_id, payload.mode)
    except NotFoundError:
        raise
    except AnalysisError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SentinelAuthError as exc:
        logger.error("Sentinel auth failed field_id=%s: %s", field_id, exc)
        raise HTTPException(
            status_code=401,
            detail="Copernicus Sentinel-2 autentifikatsiya xatosi (401). SENTINEL_HUB_CLIENT_ID va CLIENT_SECRET kalitlari noto'g'ri.",
        ) from exc
    except SentinelError as exc:
        logger.error("Sentinel analyze failed field_id=%s", field_id, exc_info=True)
        raise HTTPException(
            status_code=502, detail=f"Copernicus Sentinel-2 xizmatida xatolik: {exc}"
        ) from exc
    except Exception as exc:
        logger.exception("Field analysis failed field_id=%s", field_id)
        raise HTTPException(
            status_code=500, detail=f"Tasvirni tahlil qilishda xatolik: {exc}"
        ) from exc
    return {
        "selected_acquisition": result.selected_acquisition,
        "new_acquisitions_processed": result.new_acquisitions_processed,
        "recommendation": result.recommendation,
        "recommendation_error": result.recommendation_error,
    }


@router.get("/api/fields/{field_id}/acquisitions", response_model=list[AcquisitionOut])
async def acquisitions(
    field_id: int, repository: RepositoryDependency
) -> list[dict[str, object]]:
    repository.get_field(field_id)
    return [
        serialize_acquisition(repository, item)
        for item in repository.list_acquisitions(field_id)
    ]


@router.get("/api/fields/{field_id}/annual-metrics", response_model=AnnualSeries)
async def annual_series(
    field_id: int,
    repository: RepositoryDependency,
    writer: ArtifactWriterDependency,
    year: int = Query(ge=2015, le=2100),
) -> dict[str, object]:
    repository.get_field(field_id)
    points = metric_points(field_id, repository, writer, year=year)
    logger.info(
        "Annual metric series built field_id=%s year=%s points=%d",
        field_id,
        year,
        len(points),
    )
    return {
        "year": year,
        "indexes": list(IMPORTANT_INDEXES),
        "points": points,
    }


@router.post(
    "/api/fields/{field_id}/historical-metrics",
    response_model=HistoricalMetricsResponse,
)
async def historical_metrics(
    field_id: int,
    payload: HistoricalMetricsRequest,
    request: Request,
    repository: RepositoryDependency,
    writer: ArtifactWriterDependency,
) -> dict[str, object]:
    req_settings: Settings = request.app.state.settings
    sentinel = cast(SentinelHubClient | None, request.app.state.sentinel)
    if sentinel is None:
        raise HTTPException(status_code=503, detail="Sentinel Hub credentials sozlanmagan")
    service = AnalysisService(
        repository,
        sentinel,
        writer,
        None,
        req_settings.cloud_free_threshold,
    )
    try:
        result = await service.load_history(field_id, payload.from_date)
    except NotFoundError:
        raise
    except SentinelError as exc:
        logger.error(
            "Sentinel historical load failed field_id=%s from_date=%s",
            field_id,
            payload.from_date,
            exc_info=True,
        )
        raise HTTPException(
            status_code=502, detail=detail(req_settings, exc, "Sun'iy yo'ldosh xizmatida xatolik")
        ) from exc
    except Exception as exc:
        logger.exception(
            "Historical metric load failed field_id=%s from_date=%s",
            field_id,
            payload.from_date,
        )
        raise HTTPException(
            status_code=502, detail="Tarixiy ma'lumotlarni qayta ishlash muvaffaqiyatsiz"
        ) from exc

    today = date.today()
    points = metric_points(
        field_id,
        repository,
        writer,
        from_date=payload.from_date,
        to_date=today,
    )
    return {
        "acquisitions_found": result.acquisitions_found,
        "new_acquisitions_processed": result.new_acquisitions_processed,
        "series": {
            "from_date": payload.from_date,
            "to_date": today,
            "indexes": list(IMPORTANT_INDEXES),
            "points": points,
        },
    }


@router.get(
    "/api/fields/{field_id}/historical-metrics",
    response_model=HistoricalSeries,
)
async def saved_historical_metrics(
    field_id: int,
    repository: RepositoryDependency,
    writer: ArtifactWriterDependency,
    from_date: Annotated[date, Query()],
) -> dict[str, object]:
    repository.get_field(field_id)
    if from_date > date.today():
        raise HTTPException(
            status_code=422, detail="Boshlanish sanasi bugundan keyin bo'lishi mumkin emas"
        )
    today = date.today()
    return {
        "from_date": from_date,
        "to_date": today,
        "indexes": list(IMPORTANT_INDEXES),
        "points": metric_points(
            field_id, repository, writer, from_date=from_date, to_date=today
        ),
    }


@router.get(
    "/api/fields/{field_id}/acquisitions/{acquisition_id}/artifacts",
    response_model=list[ArtifactOut],
)
async def artifacts(
    field_id: int,
    acquisition_id: int,
    repository: RepositoryDependency,
    writer: ArtifactWriterDependency,
) -> list[dict[str, object]]:
    repository.get_acquisition(field_id, acquisition_id)
    values = repository.list_artifacts(field_id, acquisition_id)
    hotspot_coords = None
    ndre_art = next((a for a in values if a["layer_name"] == "NDRE"), None)
    if ndre_art and ndre_art.get("bbox"):
        try:
            vals_path = str(ndre_art["relative_path"]).replace("NDRE.png", "values/NDRE.npy")
            values_arr = writer.read_values(vals_path)
            valid_mask = np.isfinite(values_arr)
            hotspot_coords = calculate_hotspot_coordinates(ndre_art["bbox"], valid_mask, values_arr)
        except Exception:
            pass

    for value in values:
        value["image_url"] = (
            f"/api/fields/{field_id}/acquisitions/{acquisition_id}/images/{value['layer_name']}"
        )
        if hotspot_coords:
            value["hotspot_coordinates"] = list(hotspot_coords)
    return values


@router.get("/api/fields/{field_id}/acquisitions/{acquisition_id}/images/{layer_name}")
async def artifact_image(
    field_id: int,
    acquisition_id: int,
    layer_name: str,
    repository: RepositoryDependency,
    writer: ArtifactWriterDependency,
) -> FileResponse:
    normalized = layer_name.upper()
    if normalized not in LAYER_NAMES:
        raise HTTPException(status_code=404, detail="Ruxsat etilmagan qatlam")
    artifact = repository.get_artifact(field_id, acquisition_id, normalized)
    try:
        path = writer.resolve_existing(str(artifact["relative_path"]))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(path, media_type="image/png")


@router.get("/api/fields/{field_id}/recommendation", response_model=RecommendationOut)
async def recommendation(
    field_id: int, repository: RepositoryDependency
) -> dict[str, object]:
    field = repository.get_field(field_id)
    value = repository.get_recommendation(field_id)
    if value is None:
        acqs = repository.list_acquisitions(field_id)
        if acqs:
            crop = str(field.get("crop_name") or "Ekin")
            records = repository.index_value_records(field_id)
            metric_history: dict[str, list[float]] = {}
            for r in records:
                idx = str(r["index_name"])
                if r.get("mean_value") is not None:
                    metric_history.setdefault(idx, []).append(float(r["mean_value"]))
            content, advice = generate_expert_agronomy_advice(crop, metric_history)
            value = repository.replace_recommendation(
                field_id,
                int(acqs[0]["id"]),
                content,
                "expert-agronomy-rules",
                advice,
            )
    if value is None:
        raise HTTPException(status_code=404, detail="Tavsiya hali yaratilmagan")
    return value
