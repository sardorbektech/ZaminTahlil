"""ZaminTahlil — Mahalliy Kitoblar Ingestion va Pre-computed RAG Generator.

Ushbu skript dasturchi kompyuterida ishga tushiriladi:
1. data/books/ papkasidagi PDF kitoblarni o'qiydi;
2. 768-o'lchamli FastEmbed vektorlarini, BM25 korpusini va Bilimlar Grafini hisoblaydi;
3. data/vectors/, data/chunks/, data/graph/ va data/rag_seed.json fayllarini yaratadi;
4. Natijada og'ir PDF fayllarni Git yoki VM ga yuklash shart bo'lmaydi — faqat pre-computed RAG ma'lumotlari Git orqali VM ga o'tadi.

Foydalanish:
    python scripts/ingest_books.py
    python scripts/ingest_books.py --pdf data/books/TUPROQSHUNOSLIK.pdf
"""

import argparse
import base64
import json
import logging
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app.db import Database
from app.rag import RAGService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("ingest_books")


def export_rag_seed_json(db_path: Path, output_json: Path) -> None:
    """SQLite bazasidagi rag_documents va rag_chunks jadvallarini ko'chma rag_seed.json ga eksport qiladi."""
    logger.info("RAG ma'lumotlarini %s ga eksport qilish boshlandi...", output_json)
    db = Database(db_path)
    with db.connect() as conn:
        doc_rows = conn.execute("SELECT * FROM rag_documents ORDER BY id ASC").fetchall()
        documents = []
        for r in doc_rows:
            documents.append(
                {
                    "id": int(r["id"]),
                    "name": str(r["name"]),
                    "file_path": str(r["file_path"]),
                    "file_hash": str(r["file_hash"]),
                    "total_pages": int(r["total_pages"]),
                    "chunk_count": int(r["chunk_count"]),
                    "embedding_model": str(r["embedding_model"]),
                    "embedding_dim": int(r["embedding_dim"]),
                    "is_active": int(r["is_active"]),
                    "created_at": str(r["created_at"]),
                }
            )

        chunk_rows = conn.execute("SELECT * FROM rag_chunks ORDER BY id ASC").fetchall()
        chunks = []
        for r in chunk_rows:
            raw_blob = bytes(r["embedding"])
            chunks.append(
                {
                    "id": int(r["id"]),
                    "document_id": int(r["document_id"]),
                    "page_number": int(r["page_number"]),
                    "chunk_index": int(r["chunk_index"]),
                    "chunk_text": str(r["chunk_text"]),
                    "embedding_b64": base64.b64encode(raw_blob).decode("ascii"),
                }
            )

    payload = {
        "version": "1.0",
        "exported_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "documents": documents,
        "chunks": chunks,
    }

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    size_mb = output_json.stat().st_size / (1024 * 1024)
    logger.info(
        "✅ RAG seed fayli muvaffaqiyatli saqlandi: %s (Hajmi: %.2f MB, %d kitob, %d fragment)",
        output_json,
        size_mb,
        len(documents),
        len(chunks),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="ZaminTahlil RAG Offline Ingestion Tool")
    parser.add_argument(
        "--pdf",
        type=str,
        default=None,
        help="Aynan bitta PDF faylni indekslash (masalan: data/books/TUPROQSHUNOSLIK.pdf)",
    )
    parser.add_argument(
        "--db",
        type=str,
        default=str(ROOT_DIR / "data" / "zamintahlil.sqlite3"),
        help="SQLite ma'lumotlar bazasi fayli manzili",
    )
    parser.add_argument(
        "--books-dir",
        type=str,
        default=str(ROOT_DIR / "data" / "books"),
        help="PDF kitoblar joylashgan papka",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="nomic-ai/nomic-embed-text-v1.5",
        help="FastEmbed embedding modeli (768-dim)",
    )
    args = parser.parse_args()

    db_path = Path(args.db)
    db = Database(db_path)
    db.initialize()

    rag_service = RAGService(model_name=args.model, similarity_threshold=0.40, base_dir=ROOT_DIR / "data")

    if args.pdf:
        target_pdf = Path(args.pdf)
        if not target_pdf.is_file():
            logger.error("Ko'rsatilgan PDF fayl topilmadi: %s", target_pdf)
            sys.exit(1)
        pdf_files = [target_pdf]
    else:
        books_dir = Path(args.books_dir)
        books_dir.mkdir(parents=True, exist_ok=True)
        pdf_files = sorted(
            [p for p in books_dir.iterdir() if p.is_file() and p.suffix.lower() == ".pdf"],
            key=lambda x: x.name,
        )

    if not pdf_files:
        logger.warning(
            "%s papkasida PDF kitoblar topilmadi. Agar data/rag_seed.json mavjud bo'lsa, uni bazaga tiklaymiz.",
            args.books_dir,
        )
        seed_path = ROOT_DIR / "data" / "rag_seed.json"
        if seed_path.is_file():
            db.seed_rag_if_empty()
        return

    logger.info("Jami %d ta PDF kitob topildi:", len(pdf_files))
    for p in pdf_files:
        logger.info(" - %s (%.2f MB)", p.name, p.stat().st_size / (1024 * 1024))

    for idx, pdf_path in enumerate(pdf_files, start=1):
        logger.info("\n[%d/%d] Indekslanmoqda: %s", idx, len(pdf_files), pdf_path.name)
        res = rag_service.ingest_pdf(pdf_path, database=db, document_name=pdf_path.name)
        logger.info(
            " -> Muvaffaqiyatli: %s | %d sahifa | %d fragment | %.2f soniya",
            res["name"],
            res["total_pages"],
            res["chunk_count"],
            res["elapsed_seconds"],
        )

    seed_path = ROOT_DIR / "data" / "rag_seed.json"
    export_rag_seed_json(db_path, seed_path)

    logger.info("======================================================================")
    logger.info("[MUVAFFAQ TARZDA TUGADI] Barcha PDF kitoblar embedding va Bilimlar Grafiga o'tkazildi!")
    logger.info("Endi faqat quyidagi fayllarni Git ga commit qilishingiz kifoya:")
    logger.info("   git add data/rag_seed.json data/vectors/ data/chunks/ data/graph/")
    logger.info('   git commit -m "feat(rag): update precomputed RAG embeddings and knowledge graph"')
    logger.info("======================================================================")


if __name__ == "__main__":
    main()
