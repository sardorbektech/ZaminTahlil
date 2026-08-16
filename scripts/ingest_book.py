"""Agronomiya kitoblarini (PDF) ZaminTahlil RAG bilimlar bazasiga kiritish skripti.

Foydalanish:
    python scripts/ingest_book.py "C:/kitoblar/agronomiya_qollanma.pdf"
    python scripts/ingest_book.py "C:/kitoblar/paxtachilik.pdf" --name "Paxtachilik qo'llanmasi"
"""

import argparse
import sys
from pathlib import Path

# Loyiha ildiz katalogini sys.path ga qo'shish
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app.config import get_settings
from app.db import Database
from app.rag import RAGService


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Agronom kitoblarini (PDF) ZaminTahlil RAG bazasiga kiritish"
    )
    parser.add_argument("pdf_path", help="Kiritilishi kerak bo'lgan PDF fayl manzili")
    parser.add_argument("--name", help="Kitobning ko'rsatiladigan nomi (ixtiyoriy)")
    args = parser.parse_args()

    settings = get_settings()
    database = Database(settings.database_path)
    database.initialize()

    rag_service = RAGService(
        model_name=settings.rag_model_name,
        similarity_threshold=settings.rag_similarity_threshold,
    )

    try:
        result = rag_service.ingest_pdf(
            pdf_path=args.pdf_path,
            database=database,
            document_name=args.name,
        )
        print(f"Muvaffaqiyatli yakunlandi: ID={result['document_id']}, fragmentlar={result['chunk_count']}")
    except Exception as exc:
        print(f"Xatolik yuz berdi: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
