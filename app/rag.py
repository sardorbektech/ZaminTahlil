from __future__ import annotations

import __main__
import concurrent.futures
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import pickle
import re
import sys
import time
from typing import Any, Iterator, List, Optional, Set, Tuple

import numpy as np
import pypdf

logger = logging.getLogger(__name__)

# ANSI Rangli formatlash
_CYAN = "\033[96m"
_GREEN = "\033[92m"
_YELLOW = "\033[93m"
_RED = "\033[91m"
_PURPLE = "\033[95m"
_BOLD = "\033[1m"
_RESET = "\033[0m"


def _safe_print(*args: Any, **kwargs: Any) -> None:
    try:
        print(*args, **kwargs)
    except (UnicodeEncodeError, Exception):
        msg = " ".join(str(a) for a in args)
        clean = msg.encode("ascii", errors="backslashreplace").decode("ascii")
        print(clean, **kwargs)


# ─────────────────────────────────────────────────────────────
# 1. Bilimlar Grafi (Knowledge Graph) Data Strukturalari
# ─────────────────────────────────────────────────────────────
@dataclass
class Node:
    id: str
    type: str
    description: Optional[str] = None


@dataclass
class Edge:
    source: str
    target: str
    type: str
    description: Optional[str] = None


@dataclass
class Graph:
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)


# Pickle deserializatsiyasi uchun __main__ ga ham bog'laymiz
__main__.Node = Node
__main__.Edge = Edge
__main__.Graph = Graph


# ─────────────────────────────────────────────────────────────
# 2. RAG Chunk va Natijalar Modeli
# ─────────────────────────────────────────────────────────────
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
    strategy: str = "dense"


@dataclass(frozen=True)
class RAGSearchResult:
    chunks: list[RAGChunk]
    active_book_names: list[str]
    total_scanned_chunks: int
    dense_top_score: float
    rerank_top_score: float
    elapsed_ms: float
    step_logs: list[str]
    rag_strategy: str = "all_in_one"
    rag_source_title: str = "⚡ All-in-One RAG"
    graph_context: str | None = None


# ─────────────────────────────────────────────────────────────
# 3. Pure Python / NumPy BM25 (Okapi) Qidiruv Dvigateli
# ─────────────────────────────────────────────────────────────
class BM25Scorer:
    """O'zbek va rus tillaridagi agronomik matnlar uchun yuqori tezlikdagi BM25Okapi dvigateli."""

    def __init__(self, corpus: list[list[str]], k1: float = 1.5, b: float = 0.75) -> None:
        self.corpus_size = len(corpus)
        self.k1 = k1
        self.b = b
        self.doc_lens = [len(doc) for doc in corpus]
        self.avg_doc_len = (
            sum(self.doc_lens) / self.corpus_size if self.corpus_size > 0 else 1.0
        )
        self.df: dict[str, int] = defaultdict(int)
        self.doc_term_freqs: list[Counter[str]] = []

        for doc in corpus:
            freqs = Counter(doc)
            self.doc_term_freqs.append(freqs)
            for term in freqs:
                self.df[term] += 1

        self.idf: dict[str, float] = {}
        for term, freq in self.df.items():
            self.idf[term] = math.log(
                (self.corpus_size - freq + 0.5) / (freq + 0.5) + 1.0
            )

    def get_scores(self, query_tokens: list[str]) -> np.ndarray:
        scores = np.zeros(self.corpus_size, dtype=np.float32)
        if self.corpus_size == 0 or not query_tokens:
            return scores

        for token in query_tokens:
            if token not in self.idf:
                continue
            idf_val = self.idf[token]
            for i, freqs in enumerate(self.doc_term_freqs):
                tf = freqs.get(token, 0)
                if tf == 0:
                    continue
                denom = tf + self.k1 * (
                    1.0 - self.b + self.b * (self.doc_lens[i] / self.avg_doc_len)
                )
                scores[i] += idf_val * (tf * (self.k1 + 1.0) / denom)
        return scores


# ─────────────────────────────────────────────────────────────
# 4. Gibrid RAG Yordamchi Funksiyalari (RRF, MMR, Tokenizatsiya)
# ─────────────────────────────────────────────────────────────
def _tokenize(text: str) -> list[str]:
    """Matnni tozalab, 2 va undan ortiq harfli tokenlarga ajratadi."""
    tokens = re.findall(r"[a-zA-Z0-9а-яА-Яʻʻ’'óǵúshchñ]+", text.lower())
    return [t for t in tokens if len(t) >= 2]


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().strip())


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    return float(np.dot(a, b) / denom) if denom > 0 else 0.0


def _rrf_fusion(
    ranked_lists: list[list[tuple[int, float]]], k: int = 60
) -> list[tuple[int, float]]:
    """Reciprocal Rank Fusion — bir nechta qidiruv ro'yxatlarini RRF bali orqali birlashtiradi."""
    scores: dict[int, float] = defaultdict(float)
    for ranked in ranked_lists:
        for rank, (doc_idx, _) in enumerate(ranked, start=1):
            scores[doc_idx] += 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)


def _mmr_select(
    candidate_indices: list[int],
    embeddings: list[np.ndarray],
    query_embedding: np.ndarray,
    top_n: int,
    lambda_mult: float = 0.65,
) -> list[int]:
    """Maximal Marginal Relevance — relevanlik va xilma-xillikni muvozanatlab deduplikatsiya qiladi."""
    if len(candidate_indices) <= top_n:
        return candidate_indices

    cand_embs = [embeddings[idx] for idx in candidate_indices]
    rel_scores = [_cosine(query_embedding, emb) for emb in cand_embs]

    selected: list[int] = []
    remaining = list(range(len(candidate_indices)))

    for _ in range(top_n):
        if not remaining:
            break
        if not selected:
            best_local = max(remaining, key=lambda i: rel_scores[i])
        else:

            def mmr_score(i: int) -> float:
                rel = lambda_mult * rel_scores[i]
                sim = max(
                    _cosine(cand_embs[i], cand_embs[j]) for j in selected
                )
                return rel - (1.0 - lambda_mult) * sim

            best_local = max(remaining, key=mmr_score)

        selected.append(best_local)
        remaining.remove(best_local)

    return [candidate_indices[idx] for idx in selected]


# ─────────────────────────────────────────────────────────────
# 5. Graph RAG Traversal va Qidiruv Yordamchilari
# ─────────────────────────────────────────────────────────────
def _token_overlap_score(query_tokens: list[str], text: str) -> float:
    if not text or not query_tokens:
        return 0.0
    norm = _normalize(text)
    score = 0.0
    for token in query_tokens:
        if token in norm:
            score += 1.0
        elif len(token) >= 4 and token[: int(len(token) * 0.65)] in norm:
            score += 0.5
    return score / len(query_tokens)


def _score_node(node: Node, query_tokens: list[str]) -> float:
    id_score = _token_overlap_score(query_tokens, node.id) * 1.5
    desc_score = _token_overlap_score(query_tokens, node.description or "")
    return id_score + desc_score


def _score_edge(edge: Edge, query_tokens: list[str]) -> float:
    src = _token_overlap_score(query_tokens, edge.source)
    tgt = _token_overlap_score(query_tokens, edge.target)
    typ = _token_overlap_score(query_tokens, edge.type)
    dsc = _token_overlap_score(query_tokens, edge.description or "") * 0.5
    return max(src, tgt) + typ + dsc


def _bfs_expand(
    seed_node_ids: set[str],
    graph: Graph,
    depth: int = 2,
    max_nodes: int = 30,
) -> tuple[set[str], set[tuple[str, str, str]]]:
    """Seed tugunlaridan boshlab BFS orqali bog'liq qo'shni tugunlar va munosabatlarni yig'adi."""
    adjacency: dict[str, list[tuple[str, Edge]]] = defaultdict(list)
    for edge in graph.edges:
        adjacency[edge.source].append((edge.target, edge))
        adjacency[edge.target].append((edge.source, edge))

    visited_nodes: set[str] = set(seed_node_ids)
    visited_edges: set[tuple[str, str, str]] = set()
    queue = deque([(nid, 0) for nid in seed_node_ids])

    while queue and len(visited_nodes) < max_nodes:
        current_id, current_depth = queue.popleft()
        if current_depth >= depth:
            continue
        for neighbor_id, edge in adjacency.get(current_id, []):
            edge_key = (edge.source, edge.target, edge.type)
            visited_edges.add(edge_key)
            if neighbor_id not in visited_nodes and len(visited_nodes) < max_nodes:
                visited_nodes.add(neighbor_id)
                queue.append((neighbor_id, current_depth + 1))

    return visited_nodes, visited_edges


def _build_graph_context(
    nodes_by_id: dict[str, Node],
    edge_set: set[tuple[str, str, str]],
    all_graphs: list[Graph],
    top_k: int = 30,
) -> str:
    lines: list[str] = []
    sorted_nodes = list(nodes_by_id.items())
    for nid, node in sorted_nodes[: top_k // 2]:
        lines.append(
            f"[Ob'ekt] {nid} | turi: {node.type} | tavsif: {node.description or '—'}"
        )

    for src, tgt, typ in list(edge_set)[: top_k // 2]:
        edge_obj = None
        for graph in all_graphs:
            edge_obj = next(
                (
                    e
                    for e in graph.edges
                    if e.source == src and e.target == tgt and e.type == typ
                ),
                None,
            )
            if edge_obj:
                break
        desc = edge_obj.description if edge_obj and edge_obj.description else "—"
        lines.append(f"[Munosabat] {src} --[{typ}]--> {tgt} | izoh: {desc}")

    return "\n".join(lines) if lines else ""


# ─────────────────────────────────────────────────────────────
# 6. Agronomik Bilimlar Grafini Avtomatik Ekstraksiya Qilish
# ─────────────────────────────────────────────────────────────
AGRO_ENTITIES_PATTERNS: list[tuple[str, str, str]] = [
    (r"\b(paxta|g‘o‘za|bug‘doy|makkajo‘xori|sholi|soya|kungaboqar|beda)\b", "Ekin turi", "Qishloq xo'jaligi ekini"),
    (r"\b(azot|fosfor|kaliy|karbamid|ammofos|selitra|superfosfat|gumus)\b", "O‘g‘it / Ozuqa", "Mineral yoki organik ozuqa elementi"),
    (r"\b(bo‘z tuproq|sho‘rxok|qumloq|gilli|og‘ir gilli|allyuvial|chirindili)\b", "Tuproq turi", "Tuproq mexanik va genetik qatlami"),
    (r"\b(vilt|zang|ildiz chirishi|fuzarioz|alternarioz|xloroz|nekroz|shira|ko‘sak qurti|o‘rgimchakkana)\b", "Kasallik / Zararkunanda", "Fitopatologik xavf va zararkunanda"),
    (r"\b(NDVI|NDRE|NDMI|SAVI|EVI|BSI|LAI|NDWI|MSI|NDSI)\b", "Spektral Indeks", "Sentinel-2 masofaviy biofizik monitoring ko'rsatkichi"),
    (r"\b(tomchilatib sug‘orish|egatlab sug‘orish|sho‘r yuvish|chopiq|kultivatsiya|defoliatsiya)\b", "Agrotexnik tadbir", "Dala parvarishi va melioratsiya usuli"),
]


def extract_agronomic_graph_from_chunks(chunks: list[str], doc_name: str) -> Graph:
    """PDF bo'laklaridan agronomik tushunchalar va bog'lanishlarni ajratib Graph ob'ektini tuzadi."""
    nodes_map: dict[str, Node] = {}
    edges_list: list[Edge] = []

    # Asosiy manba tuguni
    nodes_map[doc_name] = Node(id=doc_name, type="Kitob / Darslik", description=f"Agronomik manba: {doc_name}")

    for text in chunks:
        found_in_chunk: list[Node] = []
        for pattern, node_type, default_desc in AGRO_ENTITIES_PATTERNS:
            matches = set(re.findall(pattern, text, flags=re.IGNORECASE))
            for match in matches:
                name = match.strip().capitalize()
                if name not in nodes_map:
                    nodes_map[name] = Node(id=name, type=node_type, description=default_desc)
                found_in_chunk.append(nodes_map[name])

        # Bir bo'lakda birga uchragan entitiylar orasida munosabat o'rnatish
        for i in range(len(found_in_chunk)):
            edges_list.append(
                Edge(source=doc_name, target=found_in_chunk[i].id, type="o'z_ichiga_oladi", description="Agronomik qo'llanmada tushuntirilgan")
            )
            for j in range(i + 1, min(i + 4, len(found_in_chunk))):
                edges_list.append(
                    Edge(
                        source=found_in_chunk[i].id,
                        target=found_in_chunk[j].id,
                        type="agronomik_bog'liqlik",
                        description=f"{found_in_chunk[i].id} va {found_in_chunk[j].id} o'rtasidagi agrotexnik aloqa",
                    )
                )

    return Graph(nodes=list(nodes_map.values()), edges=edges_list)


# ─────────────────────────────────────────────────────────────
# 7. Asosiy RAG Xizmati (RAGService)
# ─────────────────────────────────────────────────────────────
class RAGService:
    def __init__(
        self,
        model_name: str = "nomic-ai/nomic-embed-text-v1.5",
        similarity_threshold: float = 0.40,
        base_dir: str | Path = "data",
    ) -> None:
        self.model_name = model_name
        self.similarity_threshold = similarity_threshold
        self.base_dir = Path(base_dir)
        self.books_dir = self.base_dir / "books"
        self.vectors_dir = self.base_dir / "vectors"
        self.graphs_dir = self.base_dir / "graph"
        self.chunks_dir = self.base_dir / "chunks"

        # Papkalarni avtomatik yaratish
        for d in (self.books_dir, self.vectors_dir, self.graphs_dir, self.chunks_dir):
            d.mkdir(parents=True, exist_ok=True)

        self._embedder: Any = None
        self._cached_graphs: list[Graph] | None = None

    def _get_embedder(self) -> Any:
        if self._embedder is None:
            try:
                from fastembed import TextEmbedding

                logger.info("Initializing fastembed 768-dim model: %s", self.model_name)
                self._embedder = TextEmbedding(model_name=self.model_name)
            except Exception as exc:
                logger.error("FastEmbed model load failed: %s", exc)
                raise RuntimeError(
                    f"FastEmbed embedding modelini yuklab bo'lmadi: {exc}"
                ) from exc
        return self._embedder

    def embed_texts(self, texts: list[str], is_query: bool = False) -> list[np.ndarray]:
        """Matnlar ro'yxatidan 768-o'lchamli L2-normallashtirilgan embedding vektorlarini hisoblaydi."""
        if not texts:
            return []
        embedder = self._get_embedder()
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
        """Bazadagi barcha indekslangan kitoblar ro'yxatini qaytaradi (PDF fayl bo'lmasa ham)."""
        self.books_dir.mkdir(parents=True, exist_ok=True)
        pdf_files_map = {
            p.name: p for p in self.books_dir.iterdir() if p.is_file() and p.suffix.lower() == ".pdf"
        }

        with database.connect() as connection:
            db_docs = connection.execute(
                "SELECT * FROM rag_documents ORDER BY created_at DESC"
            ).fetchall()

        books_list: list[dict[str, Any]] = []
        seen_names = set()

        for row in db_docs:
            name = str(row["name"])
            seen_names.add(name)
            pdf_path = pdf_files_map.get(name)
            size_mb = (
                round(pdf_path.stat().st_size / (1024 * 1024), 2)
                if pdf_path and pdf_path.exists()
                else 0.0
            )
            books_list.append(
                {
                    "id": row["id"],
                    "name": name,
                    "file_path": str(pdf_path) if pdf_path else row["file_path"],
                    "size_mb": size_mb,
                    "total_pages": row["total_pages"],
                    "chunk_count": row["chunk_count"],
                    "embedding_model": row["embedding_model"],
                    "is_active": bool(row["is_active"]),
                    "indexed": True,
                }
            )

        # Developer noutbukida yangi indekslanmagan PDF bo'lsa uni ham ko'rsatish
        for name, pdf_path in pdf_files_map.items():
            if name not in seen_names:
                size_mb = round(pdf_path.stat().st_size / (1024 * 1024), 2)
                books_list.append(
                    {
                        "id": None,
                        "name": name,
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
        """PDF kitobni o'qib, 768-dim vektorlar, BM25 korpus va Bilimlar Grafi yaratib saqlaydi."""
        path = Path(pdf_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"PDF fayl topilmadi: {path}")

        doc_name = document_name or path.name
        t0 = time.perf_counter()

        _safe_print(
            f"\n{_BOLD}{_CYAN}📚 [RAG INGEST] 768-dim model bilan PDF kitob kiritilmoqda: {doc_name}{_RESET}"
        )
        _safe_print(f"   Model: {self.model_name} (768 dimensions)")
        _safe_print(f"   Fayl manzili: {path}")

        reader = pypdf.PdfReader(str(path))
        total_pages = len(reader.pages)
        _safe_print(f"   Jami sahifalar soni: {total_pages} ta")

        raw_chunks: list[tuple[int, int, str]] = []
        for page_idx, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            page_chunks = self.chunk_text(text)
            for c_idx, chunk in enumerate(page_chunks):
                if len(chunk) > 30:
                    raw_chunks.append((page_idx, c_idx, chunk))

        if not raw_chunks:
            raise ValueError("PDF fayldan o'qish mumkin bo'lgan matn topilmadi")

        _safe_print(
            f"   Yaratilgan matn bo'laklari: {len(raw_chunks)} ta. 768-dim embedding hisoblanmoqda..."
        )

        texts_only = [item[2] for item in raw_chunks]
        embeddings = self.embed_texts(texts_only, is_query=False)
        file_hash = hashlib.sha256(path.read_bytes()).hexdigest()[:16]

        with database.connect() as connection:
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

        # 1. data/chunks/ papkasiga saqlash
        chunks_cache_file = self.chunks_dir / f"chunks_doc_{doc_id}.pkl"
        with open(chunks_cache_file, "wb") as f:
            pickle.dump(raw_chunks, f)

        # 2. data/vectors/ papkasiga saqlash
        vectors_cache_file = self.vectors_dir / f"vectors_doc_{doc_id}.pkl"
        with open(vectors_cache_file, "wb") as f:
            pickle.dump(embeddings, f)

        # 3. data/graph/ papkasiga agronomik Bilimlar Grafini ekstraksiya qilib saqlash
        doc_graph = extract_agronomic_graph_from_chunks(texts_only, doc_name)
        graphs_file = self.graphs_dir / "extracted_graphs.pkl"
        all_graphs: list[Graph] = []
        if graphs_file.exists():
            try:
                with open(graphs_file, "rb") as f:
                    loaded = pickle.load(f)
                    if isinstance(loaded, list):
                        all_graphs = [g for g in loaded if g and isinstance(g, Graph)]
            except Exception:
                all_graphs = []

        all_graphs = [g for g in all_graphs if not any(n.id == doc_name for n in g.nodes)]
        all_graphs.append(doc_graph)
        with open(graphs_file, "wb") as f:
            pickle.dump(all_graphs, f)
        self._cached_graphs = all_graphs

        elapsed = time.perf_counter() - t0
        _safe_print(f"{_BOLD}{_GREEN}✅ [RAG INGEST TUGADI] {doc_name} muvaffaqiyatli indekslandi!{_RESET}")
        _safe_print(
            f"   ID: {doc_id} | Sahifalar: {total_pages} | Bo'laklar: {len(raw_chunks)} | Graf tugunlari: {len(doc_graph.nodes)} | Vaqt: {elapsed:.2f}s\n"
        )

        return {
            "document_id": doc_id,
            "name": doc_name,
            "file_path": str(path),
            "total_pages": total_pages,
            "chunk_count": len(raw_chunks),
            "graph_nodes": len(doc_graph.nodes),
            "graph_edges": len(doc_graph.edges),
            "embedding_model": self.model_name,
            "elapsed_seconds": round(elapsed, 2),
        }

    # ─────────────────────────────────────────────────────────
    # 8. 4 Ta RAG Strategiyasining Alohida Dvigatellari
    # ─────────────────────────────────────────────────────────

    def search_naive(
        self,
        query: str,
        database: Any,
        top_k: int = 3,
        threshold: float | None = None,
        selected_doc_ids: list[int] | None = None,
    ) -> list[RAGChunk]:
        """1. NAIVE RAG: 768-dim Dense Vektor Qidiruv (FAISS/Cosine o'xshashlik)."""
        cutoff = threshold if threshold is not None else self.similarity_threshold
        with database.connect() as conn:
            if selected_doc_ids and len(selected_doc_ids) > 0:
                ph = ",".join("?" for _ in selected_doc_ids)
                rows = conn.execute(
                    f"""SELECT c.id, c.document_id, d.name AS document_name, c.page_number,
                              c.chunk_index, c.chunk_text, c.embedding
                    FROM rag_chunks c JOIN rag_documents d ON d.id = c.document_id
                    WHERE d.id IN ({ph}) AND d.is_active = 1""",
                    selected_doc_ids,
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT c.id, c.document_id, d.name AS document_name, c.page_number,
                              c.chunk_index, c.chunk_text, c.embedding
                    FROM rag_chunks c JOIN rag_documents d ON d.id = c.document_id
                    WHERE d.is_active = 1"""
                ).fetchall()

        if not rows:
            return []

        query_emb = self.embed_texts([query], is_query=True)[0]
        scored = []
        for r in rows:
            emb = np.frombuffer(r["embedding"], dtype=np.float32)
            score = float(np.dot(query_emb, emb))
            scored.append((score, r))

        scored.sort(key=lambda x: x[0], reverse=True)
        results: list[RAGChunk] = []
        for score, r in scored[:top_k]:
            if score >= cutoff or (threshold is None and len(results) == 0):
                results.append(
                    RAGChunk(
                        id=int(r["id"]),
                        document_id=int(r["document_id"]),
                        document_name=str(r["document_name"]),
                        page_number=int(r["page_number"]),
                        chunk_index=int(r["chunk_index"]),
                        text=str(r["chunk_text"]),
                        score=round(score, 4),
                        rerank_score=round(score, 4),
                        strategy="naive",
                    )
                )
        return results

    def search_advanced(
        self,
        query: str,
        database: Any,
        top_k: int = 4,
        threshold: float | None = None,
        selected_doc_ids: list[int] | None = None,
    ) -> list[RAGChunk]:
        """2. ADVANCED RAG: Multi-Query + Hybrid (Dense 768-dim + Sparse BM25) + RRF + MMR + Cross Reranker."""
        cutoff = threshold if threshold is not None else self.similarity_threshold
        with database.connect() as conn:
            if selected_doc_ids and len(selected_doc_ids) > 0:
                ph = ",".join("?" for _ in selected_doc_ids)
                rows = conn.execute(
                    f"""SELECT c.id, c.document_id, d.name AS document_name, c.page_number,
                              c.chunk_index, c.chunk_text, c.embedding
                    FROM rag_chunks c JOIN rag_documents d ON d.id = c.document_id
                    WHERE d.id IN ({ph}) AND d.is_active = 1""",
                    selected_doc_ids,
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT c.id, c.document_id, d.name AS document_name, c.page_number,
                              c.chunk_index, c.chunk_text, c.embedding
                    FROM rag_chunks c JOIN rag_documents d ON d.id = c.document_id
                    WHERE d.is_active = 1"""
                ).fetchall()

        if not rows:
            return []

        # 1. Multi-Query variants
        query_variants = [query]
        tokens = _tokenize(query)
        if len(tokens) >= 3:
            query_variants.append(" ".join(tokens[:4]))
            query_variants.append(" ".join(tokens[-4:]))

        # 2. Dense va Sparse BM25 qidiruv
        chunk_texts = [str(r["chunk_text"]) for r in rows]
        tokenized_corpus = [_tokenize(t) for t in chunk_texts]
        bm25 = BM25Scorer(tokenized_corpus)

        all_embeddings = [
            np.frombuffer(r["embedding"], dtype=np.float32) for r in rows
        ]
        dense_embs_mat = np.array(all_embeddings, dtype=np.float32)

        ranked_lists: list[list[tuple[int, float]]] = []

        for q_var in query_variants:
            # Dense
            q_emb = self.embed_texts([q_var], is_query=True)[0]
            dense_scores = np.dot(dense_embs_mat, q_emb)
            dense_ranked = sorted(
                enumerate(dense_scores), key=lambda x: x[1], reverse=True
            )[:15]
            ranked_lists.append(dense_ranked)

            # Sparse BM25
            q_toks = _tokenize(q_var)
            sparse_scores = bm25.get_scores(q_toks)
            sparse_ranked = sorted(
                enumerate(sparse_scores), key=lambda x: x[1], reverse=True
            )[:15]
            ranked_lists.append(sparse_ranked)

        # 3. RRF Fusion
        fused = _rrf_fusion(ranked_lists, k=60)
        pool_indices = [idx for idx, _ in fused[:24]]

        # 4. MMR Deduplication
        orig_q_emb = self.embed_texts([query], is_query=True)[0]
        mmr_indices = _mmr_select(
            candidate_indices=pool_indices,
            embeddings=all_embeddings,
            query_embedding=orig_q_emb,
            top_n=min(10, len(pool_indices)),
            lambda_mult=0.65,
        )

        # 5. Cross-Scoring Reranker
        query_words = set(tokens)
        reranked_results: list[tuple[float, float, Any]] = []

        for idx in mmr_indices:
            row = rows[idx]
            text = str(row["chunk_text"]).lower()
            text_words = set(_tokenize(text))

            overlap = (
                len(query_words.intersection(text_words)) / len(query_words)
                if query_words
                else 0.0
            )
            phrase_bonus = 0.15 if query.lower() in text else 0.0
            dense_s = float(np.dot(orig_q_emb, all_embeddings[idx]))

            combined = 0.60 * dense_s + 0.25 * overlap + phrase_bonus
            reranked_results.append((combined, dense_s, row))

        reranked_results.sort(key=lambda x: x[0], reverse=True)

        final_chunks: list[RAGChunk] = []
        for comb, dense_s, r in reranked_results[:top_k]:
            if comb >= cutoff or (threshold is None and len(final_chunks) == 0):
                final_chunks.append(
                    RAGChunk(
                        id=int(r["id"]),
                        document_id=int(r["document_id"]),
                        document_name=str(r["document_name"]),
                        page_number=int(r["page_number"]),
                        chunk_index=int(r["chunk_index"]),
                        text=str(r["chunk_text"]),
                        score=round(comb, 4),
                        rerank_score=round(comb, 4),
                        strategy="advanced",
                    )
                )
        return final_chunks

    def search_graph(
        self,
        query: str,
        database: Any,
        top_k: int = 30,
        threshold: float | None = None,
        selected_doc_ids: list[int] | None = None,
    ) -> tuple[str, list[RAGChunk]]:
        """3. GRAPH RAG: Entity extraction + Scored graph search + BFS expansion."""
        graphs_file = self.graphs_dir / "extracted_graphs.pkl"
        if not graphs_file.exists():
            adv_chunks = self.search_advanced(query, database=database, top_k=2, threshold=threshold, selected_doc_ids=selected_doc_ids)
            return "", adv_chunks

        try:
            with open(graphs_file, "rb") as f:
                all_graphs = pickle.load(f)
                if not isinstance(all_graphs, list):
                    all_graphs = [all_graphs]
        except Exception:
            adv_chunks = self.search_advanced(query, database=database, top_k=2, threshold=threshold, selected_doc_ids=selected_doc_ids)
            return "", adv_chunks

        query_tokens = _tokenize(query)
        if not query_tokens:
            adv_chunks = self.search_advanced(query, database=database, top_k=2, threshold=threshold, selected_doc_ids=selected_doc_ids)
            return "", adv_chunks

        scored_nodes: dict[str, tuple[float, Node, Graph]] = {}
        scored_edges: list[tuple[float, Edge, Graph]] = []

        for g in all_graphs:
            if not g:
                continue
            for node in g.nodes:
                sc = _score_node(node, query_tokens)
                if sc >= 0.20:
                    if node.id not in scored_nodes or sc > scored_nodes[node.id][0]:
                        scored_nodes[node.id] = (sc, node, g)
            for edge in g.edges:
                sc = _score_edge(edge, query_tokens)
                if sc >= 0.20:
                    scored_edges.append((sc, edge, g))

        if not scored_nodes and not scored_edges:
            adv_chunks = self.search_advanced(query, database=database, top_k=2, threshold=threshold, selected_doc_ids=selected_doc_ids)
            return "", adv_chunks

        graph_seeds: dict[int, set[str]] = defaultdict(set)
        for nid, (sc, node, g) in scored_nodes.items():
            graph_seeds[id(g)].add(nid)
        for _, edge, g in scored_edges:
            graph_seeds[id(g)].add(edge.source)
            graph_seeds[id(g)].add(edge.target)

        graph_by_id = {id(g): g for g in all_graphs if g}
        all_visited_nodes: set[str] = set()
        all_visited_edges: set[tuple[str, str, str]] = set()

        for gid, seeds in graph_seeds.items():
            g = graph_by_id.get(gid)
            if not g:
                continue
            v_nodes, v_edges = _bfs_expand(seeds, g, depth=2, max_nodes=25)
            all_visited_nodes |= v_nodes
            all_visited_edges |= v_edges

        final_nodes: dict[str, Node] = {
            nid: node for nid, (_, node, _) in scored_nodes.items()
        }
        for nid in all_visited_nodes:
            if nid not in final_nodes:
                for g in all_graphs:
                    nd = next((n for n in g.nodes if n.id == nid), None)
                    if nd:
                        final_nodes[nid] = nd
                        break

        sorted_nodes = dict(
            sorted(
                final_nodes.items(),
                key=lambda item: scored_nodes.get(item[0], (0.0,))[0],
                reverse=True,
            )[: top_k // 2]
        )

        context_str = _build_graph_context(
            nodes_by_id=sorted_nodes,
            edge_set=all_visited_edges,
            all_graphs=all_graphs,
            top_k=top_k,
        )

        return context_str, []

    def search_all_in_one(
        self,
        query: str,
        database: Any,
        top_k: int = 4,
        threshold: float | None = None,
        selected_doc_ids: list[int] | None = None,
    ) -> RAGSearchResult:
        """4. ALL-IN-ONE PARALLEL RAG: Naive, Advanced va Graph RAG ni parallel bajarib sintez qiladi."""
        cutoff = threshold if threshold is not None else self.similarity_threshold
        t0 = time.perf_counter()
        step_logs: list[str] = []

        with database.connect() as connection:
            if selected_doc_ids:
                ph = ",".join("?" for _ in selected_doc_ids)
                act_rows = connection.execute(
                    f"SELECT name FROM rag_documents WHERE id IN ({ph}) AND is_active = 1",
                    selected_doc_ids,
                ).fetchall()
            else:
                act_rows = connection.execute(
                    "SELECT name FROM rag_documents WHERE is_active = 1"
                ).fetchall()
            active_names = [str(r["name"]) for r in act_rows]

            total_chunks = connection.execute(
                "SELECT count(*) as c FROM rag_chunks c JOIN rag_documents d ON d.id = c.document_id WHERE d.is_active = 1"
            ).fetchone()["c"]

        _safe_print(f"\n{_BOLD}{'=' * 75}{_RESET}")
        _safe_print(
            f"{_BOLD}{_PURPLE}⚡ [ALL-IN-ONE PARALLEL RAG DVIGATELI]{_RESET} Savol: {_YELLOW}\"{query}\"{_RESET}"
        )
        _safe_print(
            f"   Faol kitoblar ({len(active_names)} ta): {', '.join(active_names) if active_names else 'Tanlanmagan'} | Jami bo'laklar: {total_chunks} ta"
        )

        if total_chunks == 0 or not active_names:
            _safe_print(
                f"   {_YELLOW}ℹ️  RAG bazasida faol kitob topilmadi → Umumiy LLM rejimi.{_RESET}"
            )
            _safe_print(f"{_BOLD}{'=' * 75}{_RESET}\n")
            return RAGSearchResult(
                chunks=[],
                active_book_names=[],
                total_scanned_chunks=0,
                dense_top_score=0.0,
                rerank_top_score=0.0,
                elapsed_ms=0.0,
                step_logs=["Faol kitoblar mavjud emas"],
                rag_strategy="direct_llm",
                rag_source_title="🤖 Umumiy LLM Bilimlari",
                graph_context=None,
            )

        # 3 ta RAGni bir vaqtda parallel ishga tushiramiz
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            fut_naive = executor.submit(
                self.search_naive, query, database, top_k, threshold, selected_doc_ids
            )
            fut_adv = executor.submit(
                self.search_advanced, query, database, top_k, threshold, selected_doc_ids
            )
            fut_graph = executor.submit(
                self.search_graph, query, database, 30, threshold, selected_doc_ids
            )

            naive_chunks = fut_naive.result()
            adv_chunks = fut_adv.result()
            graph_context, _ = fut_graph.result()

        # Natijalarni birlashtirish va deduplikatsiya
        unique_chunks: dict[int, RAGChunk] = {}
        for c in adv_chunks:
            if threshold is None or c.score >= cutoff:
                unique_chunks[c.id] = c
        for c in naive_chunks:
            if (threshold is None or c.score >= cutoff) and c.id not in unique_chunks:
                unique_chunks[c.id] = c

        final_chunks = sorted(
            unique_chunks.values(), key=lambda x: x.rerank_score, reverse=True
        )[:top_k]

        elapsed = (time.perf_counter() - t0) * 1000

        has_chunks = len(final_chunks) > 0
        has_graph = bool(graph_context and len(graph_context.strip()) > 20)

        if has_chunks and has_graph:
            rag_strat = "all_in_one"
            rag_title = "⚡ All-in-One RAG (Advanced + Graph)"
        elif has_chunks:
            rag_strat = "advanced"
            rag_title = "🔬 Advanced RAG (Gibrid + Reranker)"
        elif has_graph:
            rag_strat = "graph"
            rag_title = "🕸️ Graph RAG (Bilimlar Grafi)"
        else:
            rag_strat = "direct_llm"
            rag_source_title = "🤖 Umumiy LLM Bilimlari"

        _safe_print(
            f"   {_BOLD}🎯 [YAKUNIY RAG STRATEGIYASI]: {_GREEN}{rag_title if 'rag_title' in locals() else '🤖 Umumiy LLM Bilimlari'}{_RESET} ({elapsed:.1f}ms)"
        )
        if final_chunks:
            for rank, c in enumerate(final_chunks, start=1):
                _safe_print(
                    f"     ✅ #{rank} [Score: {c.score:.3f} | '{c.document_name}', {c.page_number}-bet]: \"{c.text[:90]}...\""
                )
        if has_graph:
            _safe_print(f"     🕸️ Bilimlar Grafi ob'ektlari topildi va kontekstga qo'shildi.")
        _safe_print(f"{_BOLD}{'=' * 75}{_RESET}\n")

        return RAGSearchResult(
            chunks=final_chunks,
            active_book_names=active_names,
            total_scanned_chunks=total_chunks,
            dense_top_score=final_chunks[0].score if final_chunks else 0.0,
            rerank_top_score=final_chunks[0].rerank_score if final_chunks else 0.0,
            elapsed_ms=round(elapsed, 2),
            step_logs=step_logs,
            rag_strategy=rag_strat,
            rag_source_title=rag_title if "rag_title" in locals() else "🤖 Umumiy LLM Bilimlari",
            graph_context=graph_context if has_graph else None,
        )

    def search(
        self,
        query: str,
        database: Any,
        top_k: int = 3,
        threshold: float | None = None,
        selected_doc_ids: list[int] | None = None,
        rag_mode: str = "all_in_one",
    ) -> list[RAGChunk]:
        """Universal qidiruv metodi — tanlangan strategiyaga mos RAG dvigatelini ishga tushiradi."""
        if rag_mode == "naive":
            return self.search_naive(
                query,
                database=database,
                top_k=top_k,
                threshold=threshold,
                selected_doc_ids=selected_doc_ids,
            )
        elif rag_mode == "graph":
            _, chunks = self.search_graph(
                query,
                database=database,
                top_k=top_k,
                threshold=threshold,
                selected_doc_ids=selected_doc_ids,
            )
            return chunks
        elif rag_mode == "advanced":
            return self.search_advanced(
                query,
                database=database,
                top_k=top_k,
                threshold=threshold,
                selected_doc_ids=selected_doc_ids,
            )
        else:  # all_in_one
            res = self.search_all_in_one(
                query,
                database=database,
                top_k=top_k,
                threshold=threshold,
                selected_doc_ids=selected_doc_ids,
            )
            return res.chunks
