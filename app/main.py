import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Annotated, Any, cast

import numpy as np
from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.ai import AIClient, AIError
from app.analysis import AnalysisError, AnalysisService
from app.config import Settings, get_settings
from app.constants import IMPORTANT_INDEXES, LAYER_NAMES
from app.db import Database
from app.geometry import (
    canonical_geojson_and_hash,
    geodesic_area_hectares,
    validate_polygon_geojson,
)
from app.rendering import ArtifactWriter
from app.repository import DuplicateFieldError, NotFoundError, Repository
from app.schemas import (
    AcquisitionOut,
    AnalyzeRequest,
    AnalyzeResponse,
    AnnualSeries,
    ArtifactOut,
    ChatRequest,
    ChatResponse,
    FieldCreate,
    FieldDetail,
    FieldOut,
    HistoricalMetricsRequest,
    HistoricalMetricsResponse,
    HistoricalSeries,
    RecommendationOut,
)
from fastapi.middleware.cors import CORSMiddleware
from app.sentinel import SentinelError, SentinelHubClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


def build_repository(settings: Settings) -> Repository:
    database = Database(settings.database_path)
    database.initialize()
    return Repository(database)


def build_ai(settings: Settings) -> AIClient | None:
    if not settings.openai_api_key:
        return None
    return AIClient(
        settings.openai_api_key,
        primary_model=settings.openai_primary_model,
        fallback_model=settings.openai_fallback_model,
        timeout=settings.openai_timeout_seconds,
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    app.state.settings = settings
    app.state.repository = build_repository(settings)
    app.state.artifact_writer = ArtifactWriter(settings.artifact_dir)
    app.state.ai = build_ai(settings)
    yield


app = FastAPI(title="ZaminTahlil API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def get_repository(request: Request) -> Repository:
    return cast(Repository, request.app.state.repository)


async def get_artifact_writer(request: Request) -> ArtifactWriter:
    return cast(ArtifactWriter, request.app.state.artifact_writer)


RepositoryDependency = Annotated[Repository, Depends(get_repository)]
ArtifactWriterDependency = Annotated[ArtifactWriter, Depends(get_artifact_writer)]


def serialize_acquisition(repository: Repository, value: dict[str, Any]) -> dict[str, Any]:
    return dict(value)


@app.exception_handler(NotFoundError)
async def not_found_handler(_request: Request, exc: NotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/fields", response_model=FieldOut, status_code=status.HTTP_201_CREATED)
async def create_field(payload: FieldCreate, repository: RepositoryDependency) -> dict[str, object]:
    polygon = validate_polygon_geojson(payload.geometry)
    geometry, geometry_hash = canonical_geojson_and_hash(polygon)
    try:
        return repository.create_field(
            geometry=geometry,
            geometry_hash=geometry_hash,
            area_hectares=geodesic_area_hectares(polygon),
            crop_name=payload.crop_name,
            planted_on=payload.planted_on,
            growth_stage=payload.growth_stage,
        )
    except DuplicateFieldError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/fields", response_model=list[FieldOut])
async def list_fields(repository: RepositoryDependency) -> list[dict[str, object]]:
    return repository.list_fields()


@app.get("/api/fields/{field_id}", response_model=FieldDetail)
async def field_detail(field_id: int, repository: RepositoryDependency) -> dict[str, object]:
    field = repository.get_field(field_id)
    latest = repository.select_acquisition(field_id)
    field["latest_acquisition"] = latest
    field["recommendation"] = repository.get_recommendation(field_id)
    return field


@app.post("/api/fields/{field_id}/analyze", response_model=AnalyzeResponse)
async def analyze(
    field_id: int, payload: AnalyzeRequest, request: Request, repository: RepositoryDependency
) -> dict[str, object]:
    settings: Settings = request.app.state.settings
    if not settings.sentinel_hub_client_id or not settings.sentinel_hub_client_secret:
        raise HTTPException(status_code=503, detail="Sentinel Hub credentials sozlanmagan")
    sentinel = SentinelHubClient(
        settings.sentinel_hub_client_id,
        settings.sentinel_hub_client_secret,
        timeout=settings.sentinel_timeout_seconds,
    )
    service = AnalysisService(
        repository,
        sentinel,
        request.app.state.artifact_writer,
        request.app.state.ai,
        settings.cloud_free_threshold,
    )
    try:
        result = await service.analyze(field_id, payload.mode)
    except NotFoundError:
        raise
    except AnalysisError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SentinelError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        logging.getLogger(__name__).exception("Field analysis failed field_id=%s", field_id)
        raise HTTPException(
            status_code=502, detail="Tasvirni qayta ishlash muvaffaqiyatsiz"
        ) from exc
    return {
        "selected_acquisition": result.selected_acquisition,
        "new_acquisitions_processed": result.new_acquisitions_processed,
        "recommendation": result.recommendation,
        "recommendation_error": result.recommendation_error,
    }


@app.get("/api/fields/{field_id}/acquisitions", response_model=list[AcquisitionOut])
async def acquisitions(field_id: int, repository: RepositoryDependency) -> list[dict[str, object]]:
    repository.get_field(field_id)
    return [
        serialize_acquisition(repository, item) for item in repository.list_acquisitions(field_id)
    ]


@app.get("/api/fields/{field_id}/annual-metrics", response_model=AnnualSeries)
async def annual_series(
    field_id: int,
    repository: RepositoryDependency,
    writer: ArtifactWriterDependency,
    year: int = Query(ge=2015, le=2100),
) -> dict[str, object]:
    repository.get_field(field_id)
    points = metric_points(field_id, repository, writer, year=year)
    logging.getLogger(__name__).info(
        "Annual metric series built field_id=%s year=%s points=%d", field_id, year, len(points)
    )
    return {
        "year": year,
        "indexes": list(IMPORTANT_INDEXES),
        "points": points,
    }


def _point_mean(record: dict[str, Any], writer: ArtifactWriter) -> float | None:
    """Bazadagi oldindan hisoblangan o'rtacha qiymatni o'qish; migratsiyadan
    oldingi yozuvlar uchun .npy fayldan hisoblab olishga qaytish (fallback)."""
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


@app.post(
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
    settings: Settings = request.app.state.settings
    if not settings.sentinel_hub_client_id or not settings.sentinel_hub_client_secret:
        raise HTTPException(status_code=503, detail="Sentinel Hub credentials sozlanmagan")
    sentinel = SentinelHubClient(
        settings.sentinel_hub_client_id,
        settings.sentinel_hub_client_secret,
        timeout=settings.sentinel_timeout_seconds,
    )
    service = AnalysisService(
        repository,
        sentinel,
        writer,
        None,
        settings.cloud_free_threshold,
    )
    try:
        result = await service.load_history(field_id, payload.from_date)
    except NotFoundError:
        raise
    except SentinelError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        logging.getLogger(__name__).exception(
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


@app.get(
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
        "points": metric_points(field_id, repository, writer, from_date=from_date, to_date=today),
    }


@app.get(
    "/api/fields/{field_id}/acquisitions/{acquisition_id}/artifacts",
    response_model=list[ArtifactOut],
)
async def artifacts(
    field_id: int, acquisition_id: int, repository: RepositoryDependency
) -> list[dict[str, object]]:
    repository.get_acquisition(field_id, acquisition_id)
    values = repository.list_artifacts(field_id, acquisition_id)
    for value in values:
        value["image_url"] = (
            f"/api/fields/{field_id}/acquisitions/{acquisition_id}/images/{value['layer_name']}"
        )
    return values


@app.get("/api/fields/{field_id}/acquisitions/{acquisition_id}/images/{layer_name}")
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


@app.get("/api/fields/{field_id}/recommendation", response_model=RecommendationOut)
async def recommendation(field_id: int, repository: RepositoryDependency) -> dict[str, object]:
    repository.get_field(field_id)
    value = repository.get_recommendation(field_id)
    if value is None:
        raise HTTPException(status_code=404, detail="Tavsiya hali yaratilmagan")
    return value


@app.post("/api/fields/{field_id}/chat", response_model=ChatResponse)
async def chat(
    field_id: int, payload: ChatRequest, request: Request, repository: RepositoryDependency
) -> dict[str, str]:
    field = repository.get_field(field_id)
    recommendation_value = repository.get_recommendation(field_id)
    if recommendation_value is None:
        raise HTTPException(status_code=409, detail="Avval dala tahlilini bajaring")
    ai: AIClient | None = request.app.state.ai
    if ai is None:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY sozlanmagan")
    try:
        result = await ai.chat(
            field,
            recommendation_value,
            [message.model_dump() for message in payload.messages],
        )
    except AIError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"answer": result.content, "model_name": result.model_name}


frontend_dir = Path(__file__).parent / "static"
app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
