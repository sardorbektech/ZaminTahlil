from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, File, HTTPException, Request, UploadFile

from app.deps import RAGDependency, RepositoryDependency
from app.rag import RAGService
from app.repository import Repository
from app.schemas import (
    RAGBookOut,
    RAGDocumentOut,
    RAGIndexRequest,
    RAGIngestRequest,
    RAGToggleRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["RAG"])


@router.get("/api/rag/books", response_model=list[RAGBookOut])
async def list_rag_books(
    rag: RAGDependency, repository: RepositoryDependency
) -> list[dict[str, Any]]:
    try:
        return rag.scan_books_directory(repository.database)
    except Exception as exc:
        logger.exception("Failed to scan books directory: %s", exc)
        return []


@router.post("/api/rag/books/index-file", response_model=dict[str, Any])
async def index_rag_file(
    payload: RAGIndexRequest,
    rag: RAGDependency,
    repository: RepositoryDependency,
) -> dict[str, Any]:
    file_path = rag.books_dir / payload.file_name
    if not file_path.is_file():
        raise HTTPException(
            status_code=404, detail=f"PDF kitob fayli topilmadi: {payload.file_name}"
        )
    try:
        res = rag.ingest_pdf(
            file_path, database=repository.database, document_name=payload.file_name
        )
        rag.invalidate_cache()
        return res
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("RAG indexing failed for %s: %s", payload.file_name, exc)
        raise HTTPException(
            status_code=500, detail=f"Kitobni indekslashda xatolik: {exc}"
        ) from exc


@router.post("/api/rag/books/{book_id}/toggle", response_model=dict[str, Any])
async def toggle_rag_book(
    book_id: int,
    payload: RAGToggleRequest,
    rag: RAGDependency,
    repository: RepositoryDependency,
) -> dict[str, Any]:
    res = repository.toggle_rag_document(book_id, payload.is_active)
    if res is None:
        raise HTTPException(status_code=404, detail="Kitob topilmadi")
    rag.invalidate_cache()
    return res


@router.post("/api/rag/upload", response_model=dict[str, Any])
async def upload_rag_pdf(
    file: UploadFile = File(...),
    rag: RAGDependency = None,
    repository: RepositoryDependency = None,
) -> dict[str, Any]:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Faqat PDF fayllar qabul qilinadi")
    rag.books_dir.mkdir(parents=True, exist_ok=True)
    target_path = rag.books_dir / file.filename
    try:
        content = await file.read()
        target_path.write_bytes(content)
        res = rag.ingest_pdf(
            target_path, database=repository.database, document_name=file.filename
        )
        rag.invalidate_cache()
        return res
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("PDF upload and indexing failed: %s", exc)
        raise HTTPException(
            status_code=500, detail=f"PDF yuklash va indekslashda xatolik: {exc}"
        ) from exc


@router.post("/api/rag/ingest", response_model=dict[str, Any])
async def rag_ingest(
    payload: RAGIngestRequest,
    rag: RAGDependency,
    repository: RepositoryDependency,
) -> dict[str, Any]:
    try:
        res = rag.ingest_pdf(
            pdf_path=payload.pdf_path,
            database=repository.database,
            document_name=payload.document_name,
        )
        rag.invalidate_cache()
        return res
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("RAG ingestion failed")
        raise HTTPException(status_code=500, detail=f"PDF kiritishda xatolik: {exc}") from exc


@router.get("/api/rag/documents", response_model=list[RAGDocumentOut])
async def list_rag_documents(repository: RepositoryDependency) -> list[dict[str, Any]]:
    return repository.list_rag_documents()


@router.delete("/api/rag/documents/{document_id}")
async def delete_rag_document(
    document_id: int,
    rag: RAGDependency,
    repository: RepositoryDependency,
) -> dict[str, str]:
    ok = repository.delete_rag_document(document_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Hujjat topilmadi")
    rag.invalidate_cache()
    return {"status": "deleted"}
