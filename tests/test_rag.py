from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from pypdf import PageObject, PdfWriter

from app.config import Settings
from app.db import Database
from app.main import create_app
from app.rag import RAGService


def create_sample_pdf(file_path: Path) -> None:
    pdf_content = (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Resources<</Font<</F1 4 0 R>>>>/Contents 5 0 R>>endobj\n"
        b"4 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
        b"5 0 obj<</Length 110>>stream\n"
        b"BT /F1 12 Tf 100 700 Td (Paxta yetishtirish va sug'orish agrotexnikasi bo'yicha ilmiy agronomik amaliy qo'llanma.) Tj ET\n"
        b"endstream\nendobj\n"
        b"xref\n0 6\n0000000000 65535 f \n0000000009 00000 n \n0000000056 00000 n \n0000000111 00000 n \n0000000212 00000 n \n0000000281 00000 n \n"
        b"trailer<</Size 6/Root 1 0 R>>\nstartxref\n442\n%%EOF\n"
    )
    file_path.write_bytes(pdf_content)



def test_rag_chunking() -> None:
    service = RAGService()
    text = "Paxta yetishtirishda suv rejimi juda muhim. G'o'za gullash davrida ko'p suv talab qiladi. Defoliatsiya sentabr oyida amalga oshiriladi."
    chunks = service.chunk_text(text, chunk_size=60, overlap=10)
    assert len(chunks) >= 1
    for c in chunks:
        assert len(c) > 0


def test_rag_ingest_and_search(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db_path = tmp_path / "rag_test.db"
    db = Database(db_path)
    db.initialize()

    # Manual insert sample text chunks to test search & terminal logging directly
    service = RAGService(similarity_threshold=0.40)
    doc_name = "Paxtachilik Qollanmasi"
    sample_texts = [
        "G'o'zada vilt kasalligi paydo bo'lganda barglar sarg'ayadi va ildiz qorayadi.",
        "Bug'doy ekish uchun maqbul muddat oktabr oyining birinchi o'n kunligidir.",
        "Azotli o'g'itlar vegetatsiya davrining boshida berilishi kerak.",
    ]
    embeddings = service.embed_texts(sample_texts)

    with db.connect() as conn:
        cursor = conn.execute(
            """INSERT INTO rag_documents(name, file_path, file_hash, total_pages, chunk_count, created_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'))""",
            (doc_name, "C:/test.pdf", "hash123", 1, len(sample_texts)),
        )
        doc_id = int(cursor.lastrowid or 0)
        for idx, (txt, emb) in enumerate(zip(sample_texts, embeddings, strict=True)):
            conn.execute(
                """INSERT INTO rag_chunks(document_id, page_number, chunk_index, chunk_text, embedding)
                VALUES (?, ?, ?, ?, ?)""",
                (doc_id, 1, idx, txt, emb.astype(np.float32).tobytes()),
            )

    # 1. Search for disease topic
    query = "G'o'za barglari sarg'ayishi va vilt kasalligi"
    results = service.search(query, database=db, top_k=2)

    captured = capsys.readouterr()
    assert "RAG" in captured.out
    assert "G'o'za barglari sarg'ayishi" in captured.out
    assert len(results) >= 1
    assert "vilt" in results[0].text

    # 2. Search with low relevance (should trigger fallback log)
    irrelevant_query = "Kvant fizikasi va kosmik stansiyalar"
    low_results = service.search(irrelevant_query, database=db, threshold=0.95)
    captured2 = capsys.readouterr()
    assert len(low_results) == 0
    assert "RAG" in captured2.out



def test_rag_api_endpoints(tmp_path: Path) -> None:
    books_dir = tmp_path / "books"
    books_dir.mkdir(parents=True, exist_ok=True)
    sample_pdf = books_dir / "Test_Agro_Book.pdf"
    create_sample_pdf(sample_pdf)

    settings = Settings(
        app_env="demo",
        database_path=tmp_path / "rag_api.db",
        artifact_dir=tmp_path / "artifacts",
    )
    app = create_app(settings)
    with TestClient(app) as client:
        app.state.rag.books_dir = books_dir

        # 1. List books from directory
        res = client.get("/api/rag/books")

        assert res.status_code == 200
        books = res.json()
        assert len(books) == 1
        assert books[0]["name"] == "Test_Agro_Book.pdf"
        assert books[0]["indexed"] is False

        # 2. Index file
        res = client.post("/api/rag/books/index-file", json={"file_name": "Test_Agro_Book.pdf"})
        assert res.status_code == 200
        data = res.json()
        assert data["name"] == "Test_Agro_Book.pdf"
        assert data["document_id"] > 0
        doc_id = data["document_id"]

        # 3. Check listed again
        res = client.get("/api/rag/books")
        assert res.status_code == 200
        books = res.json()
        assert books[0]["indexed"] is True
        assert books[0]["is_active"] is True

        # 4. Toggle active
        res = client.post(f"/api/rag/books/{doc_id}/toggle", json={"is_active": False})
        assert res.status_code == 200
        assert res.json()["is_active"] == 0

        # 5. List documents
        res = client.get("/api/rag/documents")
        assert res.status_code == 200
        assert len(res.json()) == 1

