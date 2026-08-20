import asyncio
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Annotated, Any, cast

import numpy as np
import pandas as pd
from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.ai import AIClient, AIError
from app.analysis import AnalysisError, AnalysisService, generate_expert_agronomy_advice
from app.config import Settings, get_settings
from app.constants import IMPORTANT_INDEXES, LAYER_NAMES
from app.db import Database
from app.geometry import (
    canonical_geojson_and_hash,
    geodesic_area_hectares,
    validate_polygon_geojson,
)
from app.rag import RAGService
from app.rendering import ArtifactWriter, calculate_hotspot_coordinates
from app.repository import DuplicateFieldError, NotFoundError, Repository
from app.schemas import (
    AcquisitionOut,
    AnalyzeRequest,
    AnalyzeResponse,
    AnnualSeries,
    ArtifactOut,
    ChatHistoryMessageOut,
    ChatRequest,
    ChatResponse,
    ChatSummaryOut,
    FeatureImportanceOut,
    FieldCreate,
    FieldDetail,
    FieldOut,
    HistoricalMetricsRequest,
    HistoricalMetricsResponse,
    HistoricalSeries,
    PhenologyPointOut,
    RAGBookOut,
    RAGDocumentOut,
    RAGIndexRequest,
    RAGIngestRequest,
    RAGSourceOut,
    RAGToggleRequest,
    RecommendationOut,
    YieldPredictRequest,
    YieldPredictResponse,
)

from app.security import SecurityHeadersMiddleware, configure_logging
from app.sentinel import SentinelError, SentinelHubClient
from app.weather import fetch_weather_data
from app.yield_service import (
    CROP_CALENDARS,
    YieldInferenceService,
    build_monthly_ml_features,
    generate_phenology_timeline,
    normalize_crop_name,
    process_raw_observations,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)


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


def build_sentinel(settings: Settings) -> SentinelHubClient | None:
    if not settings.sentinel_hub_client_id or not settings.sentinel_hub_client_secret:
        return None
    return SentinelHubClient(
        settings.sentinel_hub_client_id,
        settings.sentinel_hub_client_secret,
        timeout=settings.sentinel_timeout_seconds,
        proxy=settings.sentinel_proxy,
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    if settings.is_prod:
        configure_logging(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = settings
        app.state.repository = build_repository(settings)
        app.state.artifact_writer = ArtifactWriter(settings.artifact_dir)
        app.state.ai = build_ai(settings)
        app.state.rag = RAGService(
            model_name=settings.rag_model_name,
            similarity_threshold=settings.rag_similarity_threshold,
        )
        app.state.yield_service = YieldInferenceService(models_dir=settings.models_dir)
        sentinel = build_sentinel(settings)
        app.state.sentinel = sentinel
        try:
            yield
        finally:
            if sentinel is not None:
                await sentinel.aclose()

    fastapi_kwargs: dict[str, Any] = {
        "title": "ZaminTahlil API",
        "version": "0.2.0",
        "lifespan": lifespan,
    }
    if settings.is_prod:
        fastapi_kwargs.update(docs_url=None, redoc_url=None, openapi_url=None)
    app = FastAPI(**fastapi_kwargs)

    origins = settings.cors_origin_list
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins if settings.is_prod else (origins or ["*"]),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(SecurityHeadersMiddleware)

    def _detail(exc: Exception, generic: str) -> str:
        return generic if settings.is_prod else str(exc)

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

    if settings.is_prod:

        @app.exception_handler(Exception)
        async def unhandled_exception_handler(
            _request: Request, _exc: Exception
        ) -> JSONResponse:
            logger.exception("Unhandled API error")
            return JSONResponse(status_code=500, content={"detail": "Ichki server xatosi"})

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    # --- Fields ---
    @app.post("/api/fields", response_model=FieldOut, status_code=status.HTTP_201_CREATED)
    async def create_field(
        payload: FieldCreate, repository: RepositoryDependency
    ) -> dict[str, object]:
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
    async def field_detail(
        field_id: int, repository: RepositoryDependency
    ) -> dict[str, object]:
        field = repository.get_field(field_id)
        latest = repository.select_acquisition(field_id)
        field["latest_acquisition"] = latest
        field["recommendation"] = repository.get_recommendation(field_id)
        return field

    @app.post("/api/fields/{field_id}/analyze", response_model=AnalyzeResponse)
    async def analyze(
        field_id: int,
        payload: AnalyzeRequest,
        request: Request,
        repository: RepositoryDependency,
    ) -> dict[str, object]:
        req_settings: Settings = request.app.state.settings
        sentinel = cast(SentinelHubClient | None, request.app.state.sentinel)
        if sentinel is None:
            raise HTTPException(status_code=503, detail="Sentinel Hub credentials sozlanmagan")
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
        except SentinelError as exc:
            logger.error("Sentinel analyze failed field_id=%s", field_id, exc_info=True)
            raise HTTPException(
                status_code=502, detail=_detail(exc, "Sun'iy yo'ldosh xizmatida xatolik")
            ) from exc
        except Exception as exc:
            logger.exception("Field analysis failed field_id=%s", field_id)
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
    async def acquisitions(
        field_id: int, repository: RepositoryDependency
    ) -> list[dict[str, object]]:
        repository.get_field(field_id)
        return [
            serialize_acquisition(repository, item)
            for item in repository.list_acquisitions(field_id)
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
                status_code=502, detail=_detail(exc, "Sun'iy yo'ldosh xizmatida xatolik")
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
            "points": metric_points(
                field_id, repository, writer, from_date=from_date, to_date=today
            ),
        }

    @app.get(
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

    # --- Chat with RAG, 5-day NDVI and Persistent Summary ---
    @app.get(
        "/api/fields/{field_id}/chat/history",
        response_model=list[ChatHistoryMessageOut],
    )
    async def chat_history(
        field_id: int, repository: RepositoryDependency
    ) -> list[dict[str, Any]]:
        repository.get_field(field_id)
        return repository.list_chat_messages(field_id, limit=50)

    @app.get("/api/fields/{field_id}/chat/summary", response_model=ChatSummaryOut | None)
    async def chat_summary_endpoint(
        field_id: int, repository: RepositoryDependency
    ) -> dict[str, Any] | None:
        repository.get_field(field_id)
        return repository.get_chat_summary(field_id)

    @app.post("/api/fields/{field_id}/chat", response_model=ChatResponse)
    async def chat(
        field_id: int,
        payload: ChatRequest,
        request: Request,
        repository: RepositoryDependency,
    ) -> dict[str, Any]:
        field = repository.get_field(field_id)
        recommendation_value = repository.get_recommendation(field_id)
        if recommendation_value is None:
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
                recommendation_value = repository.replace_recommendation(
                    field_id,
                    int(acqs[0]["id"]),
                    content,
                    "expert-agronomy-rules",
                    advice,
                )
        if recommendation_value is None:
            raise HTTPException(status_code=409, detail="Avval dala tahlilini bajaring")
        ai: AIClient | None = request.app.state.ai
        if ai is None:
            raise HTTPException(status_code=503, detail="OPENAI_API_KEY sozlanmagan")

        rag: RAGService = request.app.state.rag
        database: Database = repository.database

        # 1. Foydalanuvchi so'nggi xabarini aniqlash va bazaga saqlash
        last_user_message = next(
            (m.content for m in reversed(payload.messages) if m.role == "user"),
            "",
        )
        saved_user_msg = repository.add_chat_message(field_id, "user", last_user_message)

        # 2. RAG 768-dim semantik qidiruvi va Reranker (terminalda ko'rinadi)
        rag_chunks = rag.search(
            last_user_message,
            database=database,
            top_k=3,
            selected_doc_ids=payload.selected_book_ids,
        )
        active_docs = repository.database.connect()
        with repository.database.connect() as conn:
            if payload.selected_book_ids:
                placeholders = ",".join("?" for _ in payload.selected_book_ids)
                act_rows = conn.execute(
                    f"SELECT name FROM rag_documents WHERE id IN ({placeholders}) AND is_active = 1",
                    payload.selected_book_ids,
                ).fetchall()
            else:
                act_rows = conn.execute(
                    "SELECT name FROM rag_documents WHERE is_active = 1"
                ).fetchall()
            active_book_names = [str(r["name"]) for r in act_rows]

        rag_sources_out: list[dict[str, Any]] = [
            {
                "document_name": c.document_name,
                "page_number": c.page_number,
                "score": c.score,
                "text": c.text,
            }
            for c in rag_chunks
        ]
        rag_context_str: str | None = None
        if rag_chunks:
            rag_context_str = "\n\n".join(
                f"[Manba: '{c.document_name}', {c.page_number}-bet (Score: {c.score:.2f})]\n{c.text}"
                for c in rag_chunks
            )

        # 3. So'nggi 5 ta kuzatuv NDVI (va boshqa indekslar) metrikalarini olish
        recent_records = repository.index_value_records(field_id, limit=5)
        recent_metrics: dict[str, list[dict[str, Any]]] = {name: [] for name in IMPORTANT_INDEXES}
        for rec in recent_records:
            recent_metrics[str(rec["index_name"])].append(
                {
                    "acquired_at": rec["acquired_at"],
                    "cloud_coverage": rec["cloud_coverage"],
                    "mean_ndvi": rec.get("mean_value"),
                    "min": rec.get("min_value"),
                    "max": rec.get("max_value"),
                }
            )

        # 4. Oldingi suhbat xulosasi (Summary: vaqti va xabar ID lari bilan)
        existing_summary_record = repository.get_chat_summary(field_id)
        summary_text = (
            existing_summary_record["summary_text"] if existing_summary_record else None
        )

        # 5. AI chat generatsiyasi
        try:
            result = await ai.chat(
                field=field,
                recommendation=recommendation_value,
                messages=[m.model_dump() for m in payload.messages],
                recent_ndvi_metrics=recent_metrics,
                chat_summary=summary_text,
                rag_context=rag_context_str,
                language=payload.language,
            )
        except AIError as exc:
            logger.error("AI chat failed field_id=%s", field_id, exc_info=True)
            raise HTTPException(
                status_code=502, detail=_detail(exc, "AI xizmatida xatolik")
            ) from exc

        # 6. Assistant javobini saqlash
        repository.add_chat_message(
            field_id, "assistant", result.content, rag_sources=rag_sources_out
        )

        # 7. Xulosa (Summary) ni yangilash
        all_messages = repository.list_chat_messages(field_id, limit=30)
        new_summary = await ai.generate_summary(all_messages, existing_summary=summary_text)
        repository.upsert_chat_summary(
            field_id,
            new_summary,
            message_count=len(all_messages),
            last_message_id=int(saved_user_msg["id"]),
        )

        return {
            "answer": result.content,
            "model_name": result.model_name,
            "rag_sources": rag_sources_out,
            "active_books": active_book_names,
            "summary": new_summary,
        }

    # --- RAG Management Routes ---
    @app.get("/api/rag/books", response_model=list[RAGBookOut])
    async def list_rag_books(
        request: Request, repository: RepositoryDependency
    ) -> list[dict[str, Any]]:
        rag: RAGService = request.app.state.rag
        return rag.scan_books_directory(repository.database)

    @app.post("/api/rag/books/index-file", response_model=dict[str, Any])
    async def index_rag_file(
        payload: RAGIndexRequest,
        request: Request,
        repository: RepositoryDependency,
    ) -> dict[str, Any]:
        rag: RAGService = request.app.state.rag
        file_path = rag.books_dir / payload.file_name
        if not file_path.is_file():
            raise HTTPException(status_code=404, detail=f"Fayl topilmadi: {payload.file_name}")
        return rag.ingest_pdf(file_path, database=repository.database, document_name=payload.file_name)

    @app.post("/api/rag/books/{book_id}/toggle", response_model=dict[str, Any])
    async def toggle_rag_book(
        book_id: int,
        payload: RAGToggleRequest,
        repository: RepositoryDependency,
    ) -> dict[str, Any]:
        res = repository.toggle_rag_document(book_id, payload.is_active)
        if res is None:
            raise HTTPException(status_code=404, detail="Kitob topilmadi")
        return res

    @app.post("/api/rag/upload", response_model=dict[str, Any])
    async def upload_rag_pdf(
        file: UploadFile = File(...),
        request: Request = None,
        repository: RepositoryDependency = None,
    ) -> dict[str, Any]:
        if not file.filename or not file.filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail="Faqat PDF fayllar qabul qilinadi")
        rag: RAGService = request.app.state.rag
        rag.books_dir.mkdir(parents=True, exist_ok=True)
        target_path = rag.books_dir / file.filename
        content = await file.read()
        target_path.write_bytes(content)
        return rag.ingest_pdf(target_path, database=repository.database, document_name=file.filename)

    @app.post("/api/rag/ingest", response_model=dict[str, Any])
    async def rag_ingest(payload: RAGIngestRequest, request: Request) -> dict[str, Any]:
        rag: RAGService = request.app.state.rag
        repo: Repository = request.app.state.repository
        try:
            return rag.ingest_pdf(
                pdf_path=payload.pdf_path,
                database=repo.database,
                document_name=payload.document_name,
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            logger.exception("RAG ingestion failed")
            raise HTTPException(status_code=500, detail=f"PDF kiritishda xatolik: {exc}") from exc

    @app.get("/api/rag/documents", response_model=list[RAGDocumentOut])
    async def list_rag_documents(repository: RepositoryDependency) -> list[dict[str, Any]]:
        return repository.list_rag_documents()

    @app.delete("/api/rag/documents/{document_id}")
    async def delete_rag_document(
        document_id: int, repository: RepositoryDependency
    ) -> dict[str, str]:
        ok = repository.delete_rag_document(document_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Hujjat topilmadi")
        return {"status": "deleted"}


    # --- Yield Prediction Routes ---
    @app.get("/api/yield/models")
    async def list_yield_models(request: Request) -> dict[str, Any]:
        yield_service: YieldInferenceService = request.app.state.yield_service
        models = yield_service.list_available_models()
        return {
            "models": models,
            "crops": ["cotton", "wheat"],
            "default_model": "CatBoost",
            "calendars": CROP_CALENDARS,
        }

    @app.post("/api/fields/{field_id}/predict-yield", response_model=YieldPredictResponse)
    async def predict_yield_endpoint(
        field_id: int,
        payload: YieldPredictRequest,
        request: Request,
        repository: RepositoryDependency,
    ) -> dict[str, Any]:
        t_start = time.perf_counter()
        field = repository.get_field(field_id)
        yield_service: YieldInferenceService = request.app.state.yield_service

        crop_type = normalize_crop_name(payload.crop or field.get("crop_name", "cotton"))
        crop_cal = CROP_CALENDARS.get(crop_type, CROP_CALENDARS["cotton"])

        # Koordinatalar markazini aniqlash
        coords = field["geometry"]["coordinates"][0]
        lons = [float(p[0]) for p in coords]
        lats = [float(p[1]) for p in coords]
        center_lon = float(sum(lons) / len(lons))
        center_lat = float(sum(lats) / len(lats))

        p_date = (
            payload.planting_date.isoformat()
            if payload.planting_date
            else field.get("planted_on") or crop_cal["planting_date"]
        )
        h_date = (
            payload.harvest_date.isoformat()
            if payload.harvest_date
            else crop_cal["harvest_date"]
        )
        s_start = crop_cal["season_start"]
        s_end = crop_cal["season_end"]

        # 1. Real Ob-havo ma'lumotlarini olish (Open-Meteo)
        try:
            df_w = fetch_weather_data(center_lat, center_lon, start_date=s_start, end_date=s_end)
        except Exception as exc:
            logger.warning("Weather fetch failed, creating baseline weather: %s", exc)
            dates = pd.date_range(s_start, s_end)
            df_w = pd.DataFrame(
                {
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
                    "latitude": center_lat,
                    "longitude": center_lon,
                }
            )

        # 2. S2 kuzatuvlarini to'plash
        acquisitions_list = repository.list_acquisitions(field_id)
        if acquisitions_list:
            s2_records = []
            for acq in acquisitions_list:
                dt = pd.to_datetime(acq["acquired_at"].split("T")[0])
                cc = acq.get("cloud_coverage") or 10.0
                s2_records.append(
                    {
                        "date": dt,
                        "s2_b02_blue": 0.04,
                        "s2_b03_green": 0.07,
                        "s2_b04_red": 0.05,
                        "s2_b05_red_edge_1": 0.12,
                        "s2_b06_red_edge_2": 0.22,
                        "s2_b07_red_edge_3": 0.28,
                        "s2_b08_nir": 0.38,
                        "s2_b8a_nir_narrow": 0.40,
                        "s2_b11_swir_1": 0.17,
                        "s2_b12_swir_2": 0.09,
                        "s2_cloud_percentage": float(cc),
                        "s2_cloud_probability": float(cc * 0.8),
                    }
                )
            df_s2 = pd.DataFrame(s2_records)
        else:
            dates = pd.date_range(s_start, s_end, freq="10D")
            df_s2 = pd.DataFrame(
                {
                    "date": dates,
                    "s2_b02_blue": 0.04,
                    "s2_b03_green": 0.07,
                    "s2_b04_red": 0.05,
                    "s2_b05_red_edge_1": 0.12,
                    "s2_b06_red_edge_2": 0.22,
                    "s2_b07_red_edge_3": 0.28,
                    "s2_b08_nir": 0.38,
                    "s2_b8a_nir_narrow": 0.40,
                    "s2_b11_swir_1": 0.17,
                    "s2_b12_swir_2": 0.09,
                    "s2_cloud_percentage": 5.0,
                    "s2_cloud_probability": 4.0,
                }
            )

        # S1 radar baseline
        dates_s1 = pd.date_range(s_start, s_end, freq="12D")
        df_s1 = pd.DataFrame(
            {
                "date": dates_s1,
                "s1_vv": -11.5,
                "s1_vh": -16.2,
            }
        )

        # 3. Feature engineering
        df_s2_proc, df_s1_proc, df_w_proc = process_raw_observations(
            df_s2, df_s1, df_w, planting_date=str(p_date), harvest_date=str(h_date)
        )
        df_features = build_monthly_ml_features(df_s2_proc, df_s1_proc, df_w_proc, target_year=2026)

        # 4. ML Model inferensiyasi
        model_choice = payload.model_name or "CatBoost"
        try:
            (
                yield_ha,
                yield_min,
                yield_max,
                top_features,
                actual_model,
            ) = yield_service.predict_yield(
                df_features=df_features, crop=crop_type, model_name=model_choice
            )
        except Exception as exc:
            logger.error("Yield inference failed: %s", exc)
            raise HTTPException(status_code=500, detail=f"Hosildorlik inferensiyasida xatolik: {exc}") from exc

        area_ha = float(field["area_hectares"])
        total_tons = round(yield_ha * area_ha, 2)
        total_min_tons = round(yield_min * area_ha, 2)
        total_max_tons = round(yield_max * area_ha, 2)

        timeline = generate_phenology_timeline(df_s2_proc, df_s1_proc, df_w_proc)
        exec_time = round(time.perf_counter() - t_start, 2)

        top_features_dict = [
            {"feature": f.feature, "importance": f.importance, "description": f.description}
            for f in top_features
        ]
        timeline_dict = [
            {
                "month": pt.month,
                "ndvi": pt.ndvi,
                "evi": pt.evi,
                "ndre": pt.ndre,
                "ndmi": pt.ndmi,
                "s1_vh": pt.s1_vh,
                "s1_vv_vh": pt.s1_vv_vh,
                "temp_mean": pt.temp_mean,
                "rain_sum": pt.rain_sum,
                "soil_moisture": pt.soil_moisture,
            }
            for pt in timeline
        ]

        # Bazaga saqlash
        repository.save_yield_prediction(
            field_id=field_id,
            crop=crop_type,
            model_name=actual_model,
            predicted_yield_t_ha=yield_ha,
            yield_min_expected=yield_min,
            yield_max_expected=yield_max,
            total_expected_yield_tons=total_tons,
            field_area_ha=area_ha,
            top_features=top_features_dict,
            phenology_timeline=timeline_dict,
        )

        return {
            "crop": crop_type,
            "crop_display_name": crop_cal["name"],
            "model_used": actual_model,
            "predicted_yield_t_ha": yield_ha,
            "yield_min_expected": yield_min,
            "yield_max_expected": yield_max,
            "total_expected_yield_tons": total_tons,
            "total_yield_min_tons": total_min_tons,
            "total_yield_max_tons": total_max_tons,
            "field_area_ha": area_ha,
            "top_features": top_features_dict,
            "phenology_timeline": timeline_dict,
            "features_count": df_features.shape[1],
            "execution_time_sec": exec_time,
        }

    @app.get("/api/fields/{field_id}/yield-latest", response_model=dict[str, Any] | None)
    async def get_latest_yield_endpoint(
        field_id: int, repository: RepositoryDependency
    ) -> dict[str, Any] | None:
        repository.get_field(field_id)
        latest = repository.get_latest_yield_prediction(field_id)
        if latest is None:
            return None
        area_ha = float(latest.get("field_area_ha") or 1.0)
        yield_min = float(latest.get("yield_min_expected") or 0.0)
        yield_max = float(latest.get("yield_max_expected") or 0.0)
        if "total_yield_min_tons" not in latest:
            latest["total_yield_min_tons"] = round(yield_min * area_ha, 2)
        if "total_yield_max_tons" not in latest:
            latest["total_yield_max_tons"] = round(yield_max * area_ha, 2)
        crop_name = latest.get("crop", "cotton")
        crop_cal = CROP_CALENDARS.get(crop_name, CROP_CALENDARS["cotton"])
        latest["crop_display_name"] = crop_cal["name"]
        return latest

    frontend_dir = Path(__file__).parent / "static"
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")

    return app


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


app = create_app()
