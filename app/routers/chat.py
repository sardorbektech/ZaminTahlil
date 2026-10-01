from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.ai import AIClient, AIError
from app.analysis import generate_expert_agronomy_advice
from app.constants import IMPORTANT_INDEXES
from app.db import Database
from app.deps import (
    AIDependency,
    RAGDependency,
    RepositoryDependency,
    SettingsDependency,
    detail,
)
from app.rag import RAGChunk, RAGSearchResult, RAGService
from app.schemas import (
    ChatHistoryMessageOut,
    ChatRequest,
    ChatResponse,
    ChatSummaryOut,
)
from app.spatial_zones import calculate_spatial_problem_zones


logger = logging.getLogger(__name__)

router = APIRouter(tags=["Chat"])


@router.get(
    "/api/fields/{field_id}/chat/history",
    response_model=list[ChatHistoryMessageOut],
)
async def chat_history(
    field_id: int, repository: RepositoryDependency
) -> list[dict[str, Any]]:
    repository.get_field(field_id)
    return repository.list_chat_messages(field_id, limit=50)


@router.get("/api/fields/{field_id}/chat/summary", response_model=ChatSummaryOut | None)
async def chat_summary_endpoint(
    field_id: int, repository: RepositoryDependency
) -> dict[str, Any] | None:
    repository.get_field(field_id)
    return repository.get_chat_summary(field_id)


@router.get("/api/fields/{field_id}/problem-zones")
async def get_field_problem_zones_endpoint(
    field_id: int,
    repository: RepositoryDependency,
    settings: SettingsDependency,
) -> dict[str, Any]:
    """Dala telemetriyasi bo'yicha deterministik fazoviy muammoli zonalarni qaytaradi."""
    repository.get_field(field_id)
    return calculate_spatial_problem_zones(
        field_id,
        repository,
        artifact_root=settings.artifact_dir,
    )



@router.post("/api/fields/{field_id}/chat", response_model=ChatResponse)
async def chat(
    field_id: int,
    payload: ChatRequest,
    settings: SettingsDependency,
    repository: RepositoryDependency,
    ai: AIDependency,
    rag: RAGDependency,
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
    if ai is None:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY sozlanmagan")

    database: Database = repository.database

    # 1. Foydalanuvchi so'nggi xabarini aniqlash va bazaga saqlash
    last_user_message = next(
        (m.content for m in reversed(payload.messages) if m.role == "user"),
        "",
    )
    saved_user_msg = repository.add_chat_message(field_id, "user", last_user_message)

    # 2. RAG 4-Pog'onali qidiruv dvigateli (Asyncio ThreadPool orqali non-blocking)
    rag_mode = getattr(payload, "rag_mode", "advanced") or "advanced"

    if rag_mode == "all_in_one":
        rag_result: RAGSearchResult = await asyncio.to_thread(
            rag.search_all_in_one,
            last_user_message,
            database=database,
            top_k=4,
            selected_doc_ids=payload.selected_book_ids,
        )
        rag_chunks = rag_result.chunks
        active_book_names = rag_result.active_book_names
        rag_strategy = rag_result.rag_strategy
        rag_source_title = rag_result.rag_source_title
        graph_ctx = rag_result.graph_context
    elif rag_mode == "graph":
        graph_ctx, rag_chunks = await asyncio.to_thread(
            rag.search_graph,
            last_user_message,
            database=database,
            top_k=30,
            selected_doc_ids=payload.selected_book_ids,
        )
        rag_strategy = "graph" if graph_ctx else "direct_llm"
        rag_source_title = "🕸️ Graph RAG (Bilimlar Grafi)" if graph_ctx else "🤖 Umumiy LLM Bilimlari"
    elif rag_mode == "naive":
        rag_chunks = await asyncio.to_thread(
            rag.search_naive,
            last_user_message,
            database=database,
            top_k=3,
            selected_doc_ids=payload.selected_book_ids,
        )
        rag_strategy = "naive" if rag_chunks else "direct_llm"
        rag_source_title = "📚 Naive RAG (Vektor Qidiruv)" if rag_chunks else "🤖 Umumiy LLM Bilimlari"
        graph_ctx = None
    elif rag_mode == "direct_llm":
        rag_chunks = []
        rag_strategy = "direct_llm"
        rag_source_title = "🤖 Umumiy LLM Bilimlari"
        graph_ctx = None
    else:  # advanced (default)
        rag_chunks = await asyncio.to_thread(
            rag.search_advanced,
            last_user_message,
            database=database,
            top_k=4,
            selected_doc_ids=payload.selected_book_ids,
        )
        rag_strategy = "advanced" if rag_chunks else "direct_llm"
        rag_source_title = "🔬 Advanced RAG (Gibrid + Reranker)" if rag_chunks else "🤖 Umumiy LLM Bilimlari"
        graph_ctx = None

    if rag_mode != "all_in_one":
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

    context_parts: list[str] = []
    if rag_chunks:
        chunks_text = "\n\n".join(
            f"[Manba: '{c.document_name}', {c.page_number}-bet (Score: {c.score:.2f})]\n{c.text}"
            for c in rag_chunks
        )
        context_parts.append(chunks_text)
    if graph_ctx:
        context_parts.append(f"BILIMLAR GRAFI (OB'EKTLAR VA MUNOSABATLAR):\n{graph_ctx}")

    rag_context_str: str | None = "\n\n---\n\n".join(context_parts) if context_parts else None

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

    # 5. Dala deterministik fazoviy muammoli zonalarini hisoblash
    problem_zones = calculate_spatial_problem_zones(
        field_id,
        repository,
        artifact_root=settings.artifact_dir,
    )

    # 6. AI chat generatsiyasi
    try:
        result = await ai.chat(
            field=field,
            recommendation=recommendation_value,
            messages=[m.model_dump() for m in payload.messages],
            recent_ndvi_metrics=recent_metrics,
            chat_summary=summary_text,
            rag_context=rag_context_str,
            language=payload.language,
            spatial_problem_zones=problem_zones,
        )
    except AIError as exc:
        logger.error("AI chat failed field_id=%s", field_id, exc_info=True)
        raise HTTPException(
            status_code=502, detail=detail(settings, exc, "AI xizmatida xatolik")
        ) from exc

    # 7. Assistant javobini saqlash
    repository.add_chat_message(
        field_id,
        "assistant",
        result.content,
        rag_sources=rag_sources_out,
        rag_strategy=rag_strategy,
        rag_source_title=rag_source_title,
    )

    # 8. Xulosa (Summary) ni yangilash
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
        "rag_strategy": rag_strategy,
        "rag_source_title": rag_source_title,
        "summary": new_summary,
        "problem_zones": problem_zones,
    }

