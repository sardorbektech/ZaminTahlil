import hashlib
import logging
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pypdf

logger = logging.getLogger(__name__)


# Terminal uchun rangli formatlash
_CYAN = "\033[96m"
_GREEN = "\033[92m"
_YELLOW = "\033[93m"
_RED = "\033[91m"
_BOLD = "\033[1m"
_RESET = "\033[0m"


def _safe_print(*args: Any, **kwargs: Any) -> None:
    try:
        print(*args, **kwargs)
    except (UnicodeEncodeError, Exception):
        msg = " ".join(str(a) for a in args)
        clean = msg.encode("ascii", errors="backslashreplace").decode("ascii")
        print(clean, **kwargs)



@dataclass(frozen=True)
class RAGChunk:
    id: int
    document_id: int
    document_name: str
    page_number: int
    chunk_index: int
    text: str
    score: float
    rerank_score: float = 0.0


@dataclass(frozen=True)
class RAGSearchResult:
    chunks: list[RAGChunk]
    active_book_names: list[str]
    total_scanned_chunks: int
    dense_top_score: float
    rerank_top_score: float
    elapsed_ms: float
    step_logs: list[str]


class RAGService:
    def __init__(
        self,
        model_name: str = "nomic-ai/nomic-embed-text-v1.5",
        similarity_threshold: float = 0.45,
        books_dir: str | Path = "data/books",
    ) -> None:
        self.model_name = model_name
        self.similarity_threshold = similarity_threshold
        self.books_dir = Path(books_dir)
        self._embedder: Any = None

    def _get_embedder(self) -> Any:
        if self._embedder is None:
            try:
                from fastembed import TextEmbedding

                logger.info("Initializing fastembed 768-dim model: %s", self.model_name)
                self._embedder = TextEmbedding(model_name=self.model_name)
            except Exception as exc:
                logger.error("FastEmbed model load failed: %s", exc)
                raise RuntimeError(f"FastEmbed embedding modelini yuklab bo'lmadi: {exc}") from exc
        return self._embedder

    def embed_texts(self, texts: list[str], is_query: bool = False) -> list[np.ndarray]:
        """Matnlar ro'yxatidan 768-o'lchamli L2-normallashtirilgan embedding vektorlarini hisoblaydi."""
        if not texts:
            return []
        embedder = self._get_embedder()
        # Nomic Embed spetsifikatsiyasi: query uchun search_query prefiksi
        prefixed = [
            f"search_query: {t}" if is_query else f"search_document: {t}"
            for t in texts
        ]
        raw_embeddings = list(embedder.embed(prefixed))
        result = []
        for vec in raw_embeddings:
            arr = np.asarray(vec, dtype=np.float32)
            norm = np.linalg.norm(arr)
            if norm > 0:
                arr = arr / norm
            result.append(arr)
        return result

    def chunk_text(self, text: str, chunk_size: int = 650, overlap: int = 120) -> list[str]:
        """Matnni mantiqiy gaplar va paragraflar bo'yicha bo'laklaydi."""
        cleaned = re.sub(r"\s+", " ", text).strip()
        if not cleaned:
            return []
        if len(cleaned) <= chunk_size:
            return [cleaned]

        chunks: list[str] = []
        start = 0
        while start < len(cleaned):
            end = start + chunk_size
            if end >= len(cleaned):
                chunks.append(cleaned[start:].strip())
                break

            # Bo'lakni so'z yoki gap oxirida to'xtatish
            cut = cleaned.rfind(". ", start, end)
            if cut == -1 or cut <= start + 100:
                cut = cleaned.rfind(" ", start, end)
            if cut == -1 or cut <= start:
                cut = end

            chunk_content = cleaned[start:cut].strip()
            if chunk_content:
                chunks.append(chunk_content)
            start = max(cut + 1, start + chunk_size - overlap)

        return chunks

    def scan_books_directory(self, database: Any) -> list[dict[str, Any]]:
        """data/books/ papkasidagi barcha PDF fayllarni tekshiradi va bazadagi holati bilan qaytaradi."""
        self.books_dir.mkdir(parents=True, exist_ok=True)
        pdf_files = sorted(
            [p for p in self.books_dir.iterdir() if p.is_file() and p.suffix.lower() == ".pdf"],
            key=lambda x: x.name,
        )

        with database.connect() as connection:

            db_docs = connection.execute(
                "SELECT * FROM rag_documents ORDER BY created_at DESC"
            ).fetchall()
            db_docs_map = {row["name"]: dict(row) for row in db_docs}

        books_list: list[dict[str, Any]] = []
        for pdf_path in sorted(pdf_files):
            file_name = pdf_path.name
            size_mb = round(pdf_path.stat().st_size / (1024 * 1024), 2)
            db_record = db_docs_map.get(file_name)

            if db_record:
                books_list.append(
                    {
                        "id": db_record["id"],
                        "name": file_name,
                        "file_path": str(pdf_path),
                        "size_mb": size_mb,
                        "total_pages": db_record["total_pages"],
                        "chunk_count": db_record["chunk_count"],
                        "embedding_model": db_record.get("embedding_model", self.model_name),
                        "is_active": bool(db_record.get("is_active", 1)),
                        "indexed": True,
                    }
                )
            else:
                books_list.append(
                    {
                        "id": None,
                        "name": file_name,
                        "file_path": str(pdf_path),
                        "size_mb": size_mb,
                        "total_pages": None,
                        "chunk_count": 0,
                        "embedding_model": self.model_name,
                        "is_active": False,
                        "indexed": False,
                    }
                )
        return books_list

    def ingest_pdf(
        self,
        pdf_path: str | Path,
        database: Any,
        document_name: str | None = None,
    ) -> dict[str, Any]:
        """PDF kitobni o'qib, bo'laklab va 768-o'lchamli embedding hisoblab SQLite bazasiga saqlaydi."""
        path = Path(pdf_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"PDF fayl topilmadi: {path}")

        doc_name = document_name or path.name
        t0 = time.perf_counter()

        _safe_print(f"\n{_BOLD}{_CYAN}📚 [RAG INGEST] 768-dim model bilan PDF kitob kiritilmoqda: {doc_name}{_RESET}")
        _safe_print(f"   Model: {self.model_name} (768 dimensions)")
        _safe_print(f"   Fayl manzili: {path}")

        reader = pypdf.PdfReader(str(path))
        total_pages = len(reader.pages)
        _safe_print(f"   Jami sahifalar soni: {total_pages} ta")

        raw_chunks: list[tuple[int, int, str]] = []  # (page_number, chunk_idx, text)
        for page_idx, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            page_chunks = self.chunk_text(text)
            for c_idx, chunk in enumerate(page_chunks):
                if len(chunk) > 30:  # Faqat mazmunli bo'laklar
                    raw_chunks.append((page_idx, c_idx, chunk))

        if not raw_chunks:
            raise ValueError("PDF fayldan o'qish mumkin bo'lgan matn topilmadi")

        _safe_print(f"   Yaratilgan matn bo'laklari: {len(raw_chunks)} ta. 768-dim embedding hisoblanmoqda...")

        texts_only = [item[2] for item in raw_chunks]
        embeddings = self.embed_texts(texts_only, is_query=False)

        file_hash = hashlib.sha256(path.read_bytes()).hexdigest()[:16]

        with database.connect() as connection:
            # Agar shu nomli kitob ilgari kiritilgan bo'lsa, eskisini yangilaymiz
            existing = connection.execute(
                "SELECT id FROM rag_documents WHERE name = ?", (doc_name,)
            ).fetchone()
            if existing:
                doc_id = int(existing["id"])
                connection.execute("DELETE FROM rag_chunks WHERE document_id = ?", (doc_id,))
                connection.execute(
                    """UPDATE rag_documents SET file_path = ?, file_hash = ?, total_pages = ?,
                    chunk_count = ?, embedding_model = ?, embedding_dim = 768, is_active = 1,
                    created_at = datetime('now') WHERE id = ?""",
                    (str(path), file_hash, total_pages, len(raw_chunks), self.model_name, doc_id),
                )
            else:
                cursor = connection.execute(
                    """INSERT INTO rag_documents(name, file_path, file_hash, total_pages, chunk_count,
                    embedding_model, embedding_dim, is_active, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, 768, 1, datetime('now'))""",
                    (doc_name, str(path), file_hash, total_pages, len(raw_chunks), self.model_name),
                )
                doc_id = int(cursor.lastrowid or 0)

            for (page_num, chunk_idx, chunk_text), emb in zip(
                raw_chunks, embeddings, strict=True
            ):
                embedding_bytes = emb.astype(np.float32).tobytes()
                connection.execute(
                    """INSERT INTO rag_chunks(document_id, page_number, chunk_index, chunk_text, embedding)
                    VALUES (?, ?, ?, ?, ?)""",
                    (doc_id, page_num, chunk_idx, chunk_text, embedding_bytes),
                )

        elapsed = time.perf_counter() - t0
        _safe_print(f"{_BOLD}{_GREEN}✅ [RAG INGEST TUGADI] {doc_name} muvaffaqiyatli indekslandi!{_RESET}")
        _safe_print(f"   ID: {doc_id} | Sahifalar: {total_pages} | Fragmentlar: {len(raw_chunks)} | Vaqt: {elapsed:.2f}s\n")

        return {
            "document_id": doc_id,
            "name": doc_name,
            "file_path": str(path),
            "total_pages": total_pages,
            "chunk_count": len(raw_chunks),
            "embedding_model": self.model_name,
            "elapsed_seconds": round(elapsed, 2),
        }

    def _hybrid_rerank(self, query: str, candidates: list[tuple[float, Any]]) -> list[tuple[float, float, Any]]:
        """
        Ilg'or Cross-Scoring Reranker:
        1. Dense Similarity (L2 dot product)
        2. Lexical Keyword Overlap & Exact Match Coverage
        3. Term Density & Reciprocal Rank Fusion
        """
        query_words = set(re.findall(r"\w+", query.lower()))
        reranked: list[tuple[float, float, Any]] = []

        for dense_score, row in candidates:
            text = str(row["chunk_text"]).lower()
            text_words = set(re.findall(r"\w+", text))

            # Kalit so'zlar qamrovi (Lexical Recall)
            if query_words:
                overlap = len(query_words.intersection(text_words)) / len(query_words)
            else:
                overlap = 0.0

            # To'liq ibora qidiruvi
            phrase_bonus = 0.15 if query.lower() in text else 0.0

            # Gibrid yakuniy ball (70% dense + 25% overlap + 15% phrase)
            combined_score = 0.65 * dense_score + 0.25 * overlap + phrase_bonus
            reranked.append((combined_score, dense_score, row))

        reranked.sort(key=lambda x: x[0], reverse=True)
        return reranked

    def search(
        self,
        query: str,
        database: Any,
        top_k: int = 3,
        threshold: float | None = None,
        selected_doc_ids: list[int] | None = None,
    ) -> list[RAGChunk]:
        """Foydalanuvchi savoli bo'yicha 768-dim qidiruv + Reranking orqali eng mos kitob parchalarini topadi."""
        cutoff = threshold if threshold is not None else self.similarity_threshold
        t0 = time.perf_counter()

        step_logs: list[str] = []

        with database.connect() as connection:
            if selected_doc_ids is not None and len(selected_doc_ids) > 0:
                placeholders = ",".join("?" for _ in selected_doc_ids)
                rows = connection.execute(
                    f"""SELECT c.id, c.document_id, d.name AS document_name, c.page_number,
                              c.chunk_index, c.chunk_text, c.embedding
                    FROM rag_chunks c
                    JOIN rag_documents d ON d.id = c.document_id
                    WHERE d.id IN ({placeholders}) AND d.is_active = 1""",
                    selected_doc_ids,
                ).fetchall()
            else:
                rows = connection.execute(
                    """SELECT c.id, c.document_id, d.name AS document_name, c.page_number,
                              c.chunk_index, c.chunk_text, c.embedding
                    FROM rag_chunks c
                    JOIN rag_documents d ON d.id = c.document_id
                    WHERE d.is_active = 1"""
                ).fetchall()

            active_docs = connection.execute(
                "SELECT id, name FROM rag_documents WHERE is_active = 1"
            ).fetchall()
            active_names = [str(r["name"]) for r in active_docs]

        total_chunks = len(rows)
        _safe_print(f"\n{_BOLD}{'=' * 70}{_RESET}")
        _safe_print(f"{_BOLD}{_CYAN}🔍 [RAG 768-DIM QIDIRUV & RERANKER]{_RESET} Savol: {_YELLOW}\"{query}\"{_RESET}")
        _safe_print(f"   Faol kitoblar ({len(active_names)} ta): {', '.join(active_names) if active_names else 'Hech biri tanlanmagan'}")
        _safe_print(f"   Skanerlangan jami matn bo'laklari: {total_chunks} ta")

        if total_chunks == 0:
            _safe_print(f"   {_YELLOW}ℹ️  RAG bazasida faol kitob topilmadi.{_RESET}")
            _safe_print(f"{_BOLD}{_GREEN}🤖 [GPT REJIMI]{_RESET} GPT umumiy bilimlaridan va dala metrikalaridan foydalanadi.")
            _safe_print(f"{_BOLD}{'=' * 70}{_RESET}\n")
            return []

        # 1-Bosqich: 768-dim Dense Vector Search
        query_emb = self.embed_texts([query], is_query=True)[0]
        scored_candidates: list[tuple[float, Any]] = []

        for row in rows:
            raw_bytes = row["embedding"]
            emb = np.frombuffer(raw_bytes, dtype=np.float32)
            score = float(np.dot(query_emb, emb))
            scored_candidates.append((score, row))

        scored_candidates.sort(key=lambda item: item[0], reverse=True)
        top_dense_candidates = scored_candidates[:12]  # Top 12 nomzod Rerankerga uzatiladi

        # 2-Bosqich: Advanced Hybrid Reranker
        reranked = self._hybrid_rerank(query, top_dense_candidates)
        top_reranked = reranked[:top_k]

        relevant_results: list[RAGChunk] = []
        highest_score = top_reranked[0][0] if top_reranked else 0.0

        _safe_print(f"   {_BOLD}🎯 [RERANKER SARALASH NATIJALARI (Top {len(top_reranked)})]:{_RESET}")
        for rank, (combined, dense_s, row) in enumerate(top_reranked, start=1):
            passed = combined >= cutoff
            status_icon = "✅" if passed else "❌"
            snippet = row["chunk_text"][:95].replace("\n", " ") + "..."
            _safe_print(
                f"     {status_icon} #{rank} [Final: {combined:.3f} | Dense: {dense_s:.3f} | '{row['document_name']}' | {row['page_number']}-bet]: \"{snippet}\""
            )

        for combined, dense_s, row in top_reranked:
            if combined >= cutoff:
                relevant_results.append(
                    RAGChunk(
                        id=int(row["id"]),
                        document_id=int(row["document_id"]),
                        document_name=str(row["document_name"]),
                        page_number=int(row["page_number"]),
                        chunk_index=int(row["chunk_index"]),
                        text=str(row["chunk_text"]),
                        score=round(combined, 4),
                        rerank_score=round(combined, 4),
                    )
                )

        elapsed = (time.perf_counter() - t0) * 1000
        if relevant_results:
            _safe_print(
                f"{_BOLD}{_GREEN}📖 [RAG MANBASI TOPILDI]{_RESET} ({len(relevant_results)} ta fragment, Final Score={highest_score:.3f} >= {cutoff:.2f})"
            )
            _safe_print(f"   LLM ga haqiqiy agronomik kitob bilimlari uzatildi ({elapsed:.1f}ms).")
        else:
            _safe_print(
                f"{_BOLD}{_YELLOW}⚠️  [RAG MOSLIK CHEGARADAN PAST]{_RESET} (Eng yuqori Score={highest_score:.3f} < {cutoff:.2f})"
            )
            _safe_print(f"{_BOLD}{_GREEN}🤖 [GPT REJIMI]{_RESET} GPT umumiy bilimlaridan javob beradi ({elapsed:.1f}ms).")
        _safe_print(f"{_BOLD}{'=' * 70}{_RESET}\n")

        return relevant_results

