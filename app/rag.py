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

# Terminal uchun rangli formatlash (agar Windows terminali ANSI qo'llab-quvvatlasa)
_CYAN = "\033[96m"
_GREEN = "\033[92m"
_YELLOW = "\033[93m"
_RED = "\033[91m"
_BOLD = "\033[1m"
_RESET = "\033[0m"


@dataclass(frozen=True)
class RAGChunk:
    id: int
    document_id: int
    document_name: str
    page_number: int
    chunk_index: int
    text: str
    score: float


class RAGService:
    def __init__(
        self,
        model_name: str = "BAAI/bge-small-en-v1.5",
        similarity_threshold: float = 0.50,
    ) -> None:
        self.model_name = model_name
        self.similarity_threshold = similarity_threshold
        self._embedder: Any = None

    def _get_embedder(self) -> Any:
        if self._embedder is None:
            try:
                from fastembed import TextEmbedding

                logger.info("Initializing fastembed model: %s", self.model_name)
                self._embedder = TextEmbedding(model_name=self.model_name)
            except Exception as exc:
                logger.error("FastEmbed load failed: %s", exc)
                raise RuntimeError(f"FastEmbed embedding modelini yuklab bo'lmadi: {exc}") from exc
        return self._embedder

    def embed_texts(self, texts: list[str]) -> list[np.ndarray]:
        """Matnlar ro'yxatidan L2-normallashtirilgan embedding vektorlarini hisoblaydi."""
        if not texts:
            return []
        embedder = self._get_embedder()
        raw_embeddings = list(embedder.embed(texts))
        result = []
        for vec in raw_embeddings:
            arr = np.asarray(vec, dtype=np.float32)
            norm = np.linalg.norm(arr)
            if norm > 0:
                arr = arr / norm
            result.append(arr)
        return result

    def chunk_text(self, text: str, chunk_size: int = 600, overlap: int = 100) -> list[str]:
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

    def ingest_pdf(
        self,
        pdf_path: str | Path,
        database: Any,
        document_name: str | None = None,
    ) -> dict[str, Any]:
        """PDF kitobni o'qib, bo'laklab va embedding hisoblab SQLite bazasiga saqlaydi."""
        path = Path(pdf_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"PDF fayl topilmadi: {path}")

        doc_name = document_name or path.name
        t0 = time.perf_counter()

        print(f"\n{_BOLD}{_CYAN}📚 [RAG INGEST] PDF kitobni kiritish boshlandi: {doc_name}{_RESET}")
        print(f"   Fayl manzili: {path}")

        reader = pypdf.PdfReader(str(path))
        total_pages = len(reader.pages)
        print(f"   Jami sahifalar soni: {total_pages} ta")

        raw_chunks: list[tuple[int, int, str]] = []  # (page_number, chunk_idx, text)
        for page_idx, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            page_chunks = self.chunk_text(text)
            for c_idx, chunk in enumerate(page_chunks):
                if len(chunk) > 30:  # Faqat mazmunli bo'laklar
                    raw_chunks.append((page_idx, c_idx, chunk))

        if not raw_chunks:
            raise ValueError("PDF fayldan o'qish mumkin bo'lgan matn topilmadi")

        print(f"   Yaratilgan matn bo'laklari: {len(raw_chunks)} ta. Embedding hisoblanmoqda...")

        texts_only = [item[2] for item in raw_chunks]
        embeddings = self.embed_texts(texts_only)

        file_hash = hashlib.sha256(path.read_bytes()).hexdigest()[:16]

        with database.connect() as connection:
            cursor = connection.execute(
                """INSERT INTO rag_documents(name, file_path, file_hash, total_pages, chunk_count, created_at)
                VALUES (?, ?, ?, ?, ?, datetime('now'))""",
                (doc_name, str(path), file_hash, total_pages, len(raw_chunks)),
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
        print(
            f"{_BOLD}{_GREEN}✅ [RAG INGEST TUGADI] {doc_name} muvaffaqiyatli saqlandi!{_RESET}"
        )
        print(
            f"   ID: {doc_id} | Sahifalar: {total_pages} | Fragmentlar: {len(raw_chunks)} | Vaqt: {elapsed:.2f}s\n"
        )

        return {
            "document_id": doc_id,
            "name": doc_name,
            "file_path": str(path),
            "total_pages": total_pages,
            "chunk_count": len(raw_chunks),
            "elapsed_seconds": round(elapsed, 2),
        }

    def search(
        self,
        query: str,
        database: Any,
        top_k: int = 3,
        threshold: float | None = None,
    ) -> list[RAGChunk]:
        """Foydalanuvchi savoli bo'yicha eng mos agronomik kitob parchalarini topadi."""
        cutoff = threshold if threshold is not None else self.similarity_threshold
        t0 = time.perf_counter()

        with database.connect() as connection:
            rows = connection.execute(
                """SELECT c.id, c.document_id, d.name AS document_name, c.page_number,
                          c.chunk_index, c.chunk_text, c.embedding
                FROM rag_chunks c
                JOIN rag_documents d ON d.id = c.document_id"""
            ).fetchall()

        total_chunks = len(rows)
        print(f"\n{_BOLD}{'=' * 65}{_RESET}")
        print(f"{_BOLD}{_CYAN}🔍 [RAG QIDIRUV]{_RESET} Savol: {_YELLOW}\"{query}\"{_RESET}")
        print(f"   Bazadagi jami kitob fragmentlari: {total_chunks} ta")

        if total_chunks == 0:
            print(
                f"   {_YELLOW}ℹ️  RAG bazasi bo'sh (hech qanday agronom kitobi yuklanmagan).{_RESET}"
            )
            print(
                f"{_BOLD}{_GREEN}🤖 [GPT REJIMI]{_RESET} GPT o'z umumiy agronomik bilimlaridan foydalanib javob beradi."
            )
            print(f"{_BOLD}{'=' * 65}{_RESET}\n")
            return []

        query_emb = self.embed_texts([query])[0]

        scored: list[tuple[float, Any]] = []
        for row in rows:
            raw_bytes = row["embedding"]
            emb = np.frombuffer(raw_bytes, dtype=np.float32)
            # Dot product chunki ikkala vektor ham L2 normallashtirilgan
            score = float(np.dot(query_emb, emb))
            scored.append((score, row))

        scored.sort(key=lambda item: item[0], reverse=True)
        top_candidates = scored[:top_k]

        highest_score = top_candidates[0][0] if top_candidates else 0.0
        relevant_results: list[RAGChunk] = []

        print(f"   {_BOLD}Eng yuqori 3 ta topilma:{_RESET}")
        for rank, (score, row) in enumerate(top_candidates, start=1):
            status_icon = "✅" if score >= cutoff else "❌"
            snippet = row["chunk_text"][:90].replace("\n", " ") + "..."
            print(
                f"     {status_icon} #{rank} [Score: {score:.3f} | Kitob: '{row['document_name']}' | {row['page_number']}-bet]: \"{snippet}\""
            )

        for score, row in top_candidates:
            if score >= cutoff:
                relevant_results.append(
                    RAGChunk(
                        id=int(row["id"]),
                        document_id=int(row["document_id"]),
                        document_name=str(row["document_name"]),
                        page_number=int(row["page_number"]),
                        chunk_index=int(row["chunk_index"]),
                        text=str(row["chunk_text"]),
                        score=round(score, 4),
                    )
                )

        elapsed = (time.perf_counter() - t0) * 1000
        if relevant_results:
            print(
                f"{_BOLD}{_GREEN}📖 [RAG MANBASI TOPILDI]{_RESET} ({len(relevant_results)} ta fragment, eng yuqori score={highest_score:.3f} >= {cutoff:.2f})"
            )
            print(f"   GPT ga kitob matni fakt sifatida uzatildi ({elapsed:.1f}ms).")
        else:
            print(
                f"{_BOLD}{_YELLOW}⚠️  [RAG MANBASI YETARLI EMAS]{_RESET} (Eng yuqori score={highest_score:.3f} < {cutoff:.2f})"
            )
            print(
                f"{_BOLD}{_GREEN}🤖 [GPT REJIMI]{_RESET} GPT o'z umumiy bilimlaridan va dala metrikalaridan foydalanadi ({elapsed:.1f}ms)."
            )
        print(f"{_BOLD}{'=' * 65}{_RESET}\n")

        return relevant_results
