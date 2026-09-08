from __future__ import annotations

from typing import Annotated, cast
from fastapi import Depends, Request

from app.ai import AIClient
from app.config import Settings, get_settings as get_settings_from_config
from app.rag import RAGService
from app.rendering import ArtifactWriter
from app.repository import Repository
from app.sentinel import SentinelHubClient
from app.yield_service import YieldInferenceService


def get_settings(request: Request) -> Settings:
    settings = getattr(request.app.state, "settings", None)
    return settings if settings is not None else get_settings_from_config()


def get_repository(request: Request) -> Repository:
    return cast(Repository, request.app.state.repository)


def get_artifact_writer(request: Request) -> ArtifactWriter:
    return cast(ArtifactWriter, request.app.state.artifact_writer)


def get_ai(request: Request) -> AIClient | None:
    return cast(AIClient | None, request.app.state.ai)


def get_rag(request: Request) -> RAGService:
    return cast(RAGService, request.app.state.rag)


def get_yield_service(request: Request) -> YieldInferenceService:
    return cast(YieldInferenceService, request.app.state.yield_service)


def get_sentinel(request: Request) -> SentinelHubClient | None:
    return cast(SentinelHubClient | None, getattr(request.app.state, "sentinel", None))


def detail(settings: Settings, exc: Exception, generic: str) -> str:
    return generic if settings.is_prod else str(exc)


SettingsDependency = Annotated[Settings, Depends(get_settings)]
RepositoryDependency = Annotated[Repository, Depends(get_repository)]
ArtifactWriterDependency = Annotated[ArtifactWriter, Depends(get_artifact_writer)]
AIDependency = Annotated[AIClient | None, Depends(get_ai)]
RAGDependency = Annotated[RAGService, Depends(get_rag)]
YieldServiceDependency = Annotated[YieldInferenceService, Depends(get_yield_service)]
SentinelDependency = Annotated[SentinelHubClient | None, Depends(get_sentinel)]
