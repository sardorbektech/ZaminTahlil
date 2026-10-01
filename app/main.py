from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import logging
from pathlib import Path
from typing import Any

import asyncio
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.ai import AIClient
from app.config import Settings, get_settings
from app.db import Database
from app.rag import RAGService
from app.rendering import ArtifactWriter
from app.repository import NotFoundError, Repository
from app.routers import (
    analysis_router,
    auth_router,
    chat_router,
    fields_router,
    rag_router,
    yield_router,
)
from app.routers.analysis import metric_points, serialize_acquisition
from app.security import (
    RateLimitMiddleware,
    SecurityHeadersMiddleware,
    configure_logging,
)
from app.sentinel import SentinelHubClient
from app.yield_service import YieldInferenceService

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
        bot_task: asyncio.Task[None] | None = None
        if settings.telegram_bot_token and settings.telegram_bot_token.strip():
            from app.bot import start_telegram_bot
            bot_task = asyncio.create_task(start_telegram_bot(app))
            logger.info("🤖 Telegram Bot fon rejimi pollingi ishga tushirildi.")
        else:
            logger.warning(
                "⚠️ TELEGRAM_BOT_TOKEN sozlanmagan. Telegram bot ishga tushishi uchun .env faylida "
                "TELEGRAM_BOT_TOKEN=<token> kiritilgan bo'lishi kerak."
            )

        try:
            yield
        finally:
            if bot_task is not None:
                from app.bot import stop_telegram_bot
                await stop_telegram_bot()
                bot_task.cancel()
                try:
                    await bot_task
                except (asyncio.CancelledError, Exception):
                    pass
            if getattr(app.state, "sentinel", None) is not None:
                await app.state.sentinel.aclose()


    fastapi_kwargs: dict[str, Any] = {
        "title": "ZaminTahlil API",
        "version": "0.2.0",
        "lifespan": lifespan,
    }
    if settings.is_prod:
        fastapi_kwargs.update(docs_url=None, redoc_url=None, openapi_url=None)

    app = FastAPI(**fastapi_kwargs)
    app.state.settings = settings
    app.state.repository = build_repository(settings)
    app.state.artifact_writer = ArtifactWriter(settings.artifact_dir)
    app.state.ai = build_ai(settings)
    app.state.rag = RAGService(
        model_name=settings.rag_model_name,
        similarity_threshold=settings.rag_similarity_threshold,
    )
    app.state.yield_service = YieldInferenceService(models_dir=settings.models_dir)
    app.state.sentinel = build_sentinel(settings)

    # 1. Middlewares
    origins = settings.cors_origin_list
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins if settings.is_prod else (origins or ["*"]),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RateLimitMiddleware, max_requests_per_minute=40)
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    # 2. Exception Handlers
    @app.exception_handler(NotFoundError)
    async def not_found_handler(_request: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    if settings.is_prod:
        @app.exception_handler(Exception)
        async def generic_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
            logger.exception("Unhandled error: %s", exc)
            return JSONResponse(status_code=500, content={"detail": "Ichki server xatosi"})

    # 3. Health check
    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    # 4. Modulli Routerlar
    app.include_router(auth_router)
    app.include_router(fields_router)
    app.include_router(analysis_router)
    app.include_router(chat_router)
    app.include_router(rag_router)
    app.include_router(yield_router)

    # 5. Frontend statik fayllari
    frontend_dir = Path(__file__).parent / "static"
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")

    return app


app = create_app()
