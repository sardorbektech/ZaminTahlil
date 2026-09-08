from __future__ import annotations

import logging
from pathlib import Path
import shutil
from typing import Any

from fastapi import APIRouter, HTTPException, status

from app.deps import RepositoryDependency
from app.geometry import (
    canonical_geojson_and_hash,
    geodesic_area_hectares,
    validate_polygon_geojson,
)
from app.repository import DuplicateFieldError
from app.schemas import (
    FieldCreate,
    FieldDetail,
    FieldOut,
    PurgeDatabaseRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Fields"])


@router.post("/api/fields", response_model=FieldOut, status_code=status.HTTP_201_CREATED)
async def create_field(
    payload: FieldCreate, repository: RepositoryDependency
) -> dict[str, object]:
    try:
        polygon = validate_polygon_geojson(payload.geometry)
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail=f"Noto'g'ri polygon geometriyasi: {exc}"
        ) from exc
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
        raise HTTPException(
            status_code=409,
            detail="Ushbu dala maydoni avval saqlangan (dublikat). Ro'yxatdan tanlang.",
        ) from exc


@router.get("/api/fields", response_model=list[FieldOut])
async def list_fields(repository: RepositoryDependency) -> list[dict[str, object]]:
    return repository.list_fields()


@router.get("/api/fields/{field_id}", response_model=FieldDetail)
async def field_detail(
    field_id: int, repository: RepositoryDependency
) -> dict[str, object]:
    field = repository.get_field(field_id)
    latest = repository.select_acquisition(field_id)
    field["latest_acquisition"] = latest
    field["recommendation"] = repository.get_recommendation(field_id)
    return field


@router.post("/api/database/purge-fields", response_model=dict[str, Any])
async def purge_fields_database(
    payload: PurgeDatabaseRequest,
    repository: RepositoryDependency,
) -> dict[str, Any]:
    if payload.confirmation.strip().lower() != "roziman":
        raise HTTPException(
            status_code=400,
            detail="Noto'g'ri parol. Tozalash uchun 'roziman' so'zini kiriting.",
        )

    with repository.database.connect() as conn:
        tables = [
            "fields",
            "acquisitions",
            "index_values",
            "artifacts",
            "recommendations",
            "field_chat_messages",
            "field_chat_summaries",
        ]
        for table in tables:
            conn.execute(f"DELETE FROM {table}")

    # Clear generated raster artifacts
    artifacts_dir = Path("data/artifacts")
    if artifacts_dir.exists():
        for item in artifacts_dir.iterdir():
            if item.is_dir():
                shutil.rmtree(item, ignore_errors=True)
            elif item.is_file():
                item.unlink(missing_ok=True)

    logger.warning("Fields database and artifacts purged by user confirmation.")
    return {
        "success": True,
        "message": "Barcha dala maydonlari va tahlillar bazadan to'liq tozalandi",
    }
