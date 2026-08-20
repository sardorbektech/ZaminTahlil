import json
import sqlite3
from datetime import date
from typing import Any

from app.constants import (
    IMPORTANT_INDEXES,
    INDEX_NAMES,
    LAYER_NAMES,
    MAX_STORED_ACQUISITIONS,
    RENDER_VERSION,
)
from app.db import Database, decode_json_columns, row_to_dict
from app.indices import IndexStats
from app.timeutils import iso_utc


class NotFoundError(LookupError):
    pass


class DuplicateFieldError(ValueError):
    pass


def generate_field_id() -> str:
    import secrets
    import string

    alphabet = string.ascii_lowercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(8))


class Repository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def create_field(
        self,
        *,
        geometry: dict[str, Any],
        geometry_hash: str,
        area_hectares: float,
        crop_name: str,
        planted_on: date,
        growth_stage: str,
    ) -> dict[str, Any]:
        now = iso_utc()
        public_id = generate_field_id()
        try:
            with self.database.connect() as connection:
                cursor = connection.execute(
                    """INSERT INTO fields(
                        public_id, geometry_json, geometry_hash, area_hectares, crop_name,
                        planted_on, growth_stage, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        public_id,
                        json.dumps(geometry, separators=(",", ":")),
                        geometry_hash,
                        area_hectares,
                        crop_name,
                        planted_on.isoformat(),
                        growth_stage,
                        now,
                        now,
                    ),
                )
                field_id = int(cursor.lastrowid or 0)
        except sqlite3.IntegrityError as exc:
            if "geometry_hash" in str(exc):
                raise DuplicateFieldError("Bu dala geometriyasi avval saqlangan") from exc
            raise
        return self.get_field(field_id)

    def list_fields(self) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute("SELECT * FROM fields ORDER BY created_at DESC").fetchall()
        return [decode_json_columns(row_to_dict(row), "geometry_json") for row in rows]

    def get_field(self, field_id: int | str) -> dict[str, Any]:
        with self.database.connect() as connection:
            if isinstance(field_id, int) or (isinstance(field_id, str) and field_id.isdigit()):
                row = connection.execute(
                    "SELECT * FROM fields WHERE id = ? OR public_id = ?",
                    (int(field_id), str(field_id)),
                ).fetchone()
            else:
                row = connection.execute(
                    "SELECT * FROM fields WHERE public_id = ?", (str(field_id),)
                ).fetchone()
        if row is None:
            raise NotFoundError("Dala topilmadi")
        return decode_json_columns(row_to_dict(row), "geometry_json")


    def create_acquisition_if_new(
        self,
        field_id: int,
        *,
        acquired_at: str,
        product_id: str,
        revision_key: str,
        cloud_coverage: float | None,
        metadata: dict[str, Any],
    ) -> tuple[dict[str, Any], bool]:
        now = iso_utc()
        with self.database.connect() as connection:
            cursor = connection.execute(
                """INSERT OR IGNORE INTO acquisitions(
                    field_id, acquired_at, product_id, revision_key, cloud_coverage,
                    source_metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    field_id,
                    acquired_at,
                    product_id,
                    revision_key,
                    cloud_coverage,
                    json.dumps(metadata, separators=(",", ":")),
                    now,
                ),
            )
            created = cursor.rowcount == 1
            row = connection.execute(
                """SELECT * FROM acquisitions
                WHERE field_id = ? AND product_id = ? AND revision_key = ?""",
                (field_id, product_id, revision_key),
            ).fetchone()
        assert row is not None
        return decode_json_columns(row_to_dict(row), "source_metadata_json"), created

    def mark_processing_failure(self, acquisition_id: int, message: str) -> None:
        with self.database.connect() as connection:
            connection.execute(
                "UPDATE acquisitions SET processing_error = ? WHERE id = ?",
                (message[:500], acquisition_id),
            )

    def complete_acquisition(
        self,
        acquisition_id: int,
        index_data: dict[str, tuple[str, IndexStats]],
        *,
        processed_at: str,
    ) -> None:
        total_valid = index_data["NDVI"][1].valid_pixel_count
        with self.database.connect() as connection:
            for name in INDEX_NAMES:
                relative_path, stats = index_data[name]
                connection.execute(
                    """INSERT INTO index_values(
                        acquisition_id, index_name, relative_path, valid_pixel_count,
                        mean_value, min_value, median_value, max_value
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(acquisition_id, index_name) DO UPDATE SET
                        relative_path=excluded.relative_path,
                        valid_pixel_count=excluded.valid_pixel_count,
                        mean_value=excluded.mean_value,
                        min_value=excluded.min_value,
                        median_value=excluded.median_value,
                        max_value=excluded.max_value""",
                    (
                        acquisition_id,
                        name,
                        relative_path,
                        stats.valid_pixel_count,
                        stats.mean,
                        stats.minimum,
                        stats.median,
                        stats.maximum,
                    ),
                )
            connection.execute(
                """UPDATE acquisitions SET processed_at = ?, valid_pixel_count = ?,
                fully_cloudy = ?, processing_error = NULL WHERE id = ?""",
                (processed_at, total_valid, int(total_valid == 0), acquisition_id),
            )

    def has_complete_index_values(self, acquisition_id: int) -> bool:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM index_values WHERE acquisition_id = ?",
                (acquisition_id,),
            ).fetchone()
        return row is not None and int(row["count"]) == len(INDEX_NAMES)

    def has_complete_artifacts(self, acquisition_id: int) -> bool:
        with self.database.connect() as connection:
            row = connection.execute(
                """SELECT COUNT(DISTINCT layer_name) AS count FROM artifacts
                WHERE acquisition_id = ? AND render_version = ?""",
                (acquisition_id, RENDER_VERSION),
            ).fetchone()
        return row is not None and int(row["count"]) == len(LAYER_NAMES)

    def upsert_artifact(
        self,
        *,
        acquisition_id: int,
        layer_name: str,
        bbox: list[float],
        width: int,
        height: int,
        render_version: str,
        relative_path: str,
        created_at: str,
    ) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """INSERT INTO artifacts(
                    acquisition_id, layer_name, bbox_json, width, height,
                    render_version, relative_path, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(acquisition_id, layer_name, render_version) DO UPDATE SET
                    bbox_json=excluded.bbox_json, width=excluded.width,
                    height=excluded.height, relative_path=excluded.relative_path,
                    created_at=excluded.created_at""",
                (
                    acquisition_id,
                    layer_name,
                    json.dumps(bbox),
                    width,
                    height,
                    render_version,
                    relative_path,
                    created_at,
                ),
            )

    def _acquisition_record(self, row: sqlite3.Row) -> dict[str, Any]:
        record = decode_json_columns(row_to_dict(row), "source_metadata_json")
        record["fully_cloudy"] = bool(record["fully_cloudy"])
        return record

    def list_acquisitions(
        self, field_id: int, *, processed_only: bool = True
    ) -> list[dict[str, Any]]:
        clause = (
            "AND processed_at IS NOT NULL AND EXISTS (SELECT 1 FROM index_values "
            "WHERE index_values.acquisition_id = acquisitions.id) "
            "AND EXISTS (SELECT 1 FROM artifacts WHERE "
            "artifacts.acquisition_id = acquisitions.id AND artifacts.render_version = ?)"
            if processed_only
            else ""
        )
        parameters: tuple[Any, ...] = (field_id, RENDER_VERSION) if processed_only else (field_id,)
        with self.database.connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM acquisitions WHERE field_id = ? {clause} ORDER BY acquired_at DESC",
                parameters,
            ).fetchall()
        return [self._acquisition_record(row) for row in rows]

    def get_acquisition(self, field_id: int, acquisition_id: int) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM acquisitions WHERE id = ? AND field_id = ?",
                (acquisition_id, field_id),
            ).fetchone()
        if row is None:
            raise NotFoundError("Kuzatuv topilmadi")
        return self._acquisition_record(row)

    def select_acquisition(
        self, field_id: int, *, cloud_free_threshold: float | None = None
    ) -> dict[str, Any] | None:
        conditions = [
            "field_id = ?",
            "processed_at IS NOT NULL",
            "EXISTS (SELECT 1 FROM index_values WHERE "
            "index_values.acquisition_id = acquisitions.id)",
        ]
        parameters: list[Any] = [field_id]
        if cloud_free_threshold is not None:
            conditions.extend(["valid_pixel_count > 0", "cloud_coverage <= ?"])
            parameters.append(cloud_free_threshold)
        with self.database.connect() as connection:
            row = connection.execute(
                f"SELECT * FROM acquisitions WHERE {' AND '.join(conditions)} "
                "ORDER BY acquired_at DESC LIMIT 1",
                parameters,
            ).fetchone()
        if row is None:
            return None
        return self._acquisition_record(row)

    def list_artifacts(self, field_id: int, acquisition_id: int) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """SELECT artifacts.*, index_values.mean_value, index_values.min_value,
                index_values.median_value, index_values.max_value,
                index_values.valid_pixel_count AS layer_valid_pixel_count
                FROM artifacts
                JOIN acquisitions ON acquisitions.id = artifacts.acquisition_id
                LEFT JOIN index_values ON index_values.acquisition_id = artifacts.acquisition_id
                    AND index_values.index_name = artifacts.layer_name
                WHERE artifacts.acquisition_id = ? AND acquisitions.field_id = ?
                AND artifacts.render_version = ?""",
                (acquisition_id, field_id, RENDER_VERSION),
            ).fetchall()
        return [decode_json_columns(row_to_dict(row), "bbox_json") for row in rows]

    def get_artifact(self, field_id: int, acquisition_id: int, layer_name: str) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute(
                """SELECT artifacts.* FROM artifacts
                JOIN acquisitions ON acquisitions.id = artifacts.acquisition_id
                WHERE artifacts.acquisition_id = ? AND acquisitions.field_id = ?
                AND artifacts.layer_name = ? AND artifacts.render_version = ?
                ORDER BY artifacts.created_at DESC LIMIT 1""",
                (acquisition_id, field_id, layer_name, RENDER_VERSION),
            ).fetchone()
        if row is None:
            raise NotFoundError("Tasvir qatlami topilmadi")
        return decode_json_columns(row_to_dict(row), "bbox_json")

    def replace_recommendation(
        self,
        field_id: int,
        acquisition_id: int,
        content: str,
        model_name: str,
        advice: dict[str, list[str]] | None = None,
    ) -> dict[str, Any]:
        now = iso_utc()
        advice_json = json.dumps(
            advice or {"red": [], "yellow": [], "green": []},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        with self.database.connect() as connection:
            connection.execute(
                """INSERT INTO recommendations(
                    field_id, acquisition_id, content, advice_json, model_name, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(field_id) DO UPDATE SET acquisition_id=excluded.acquisition_id,
                    content=excluded.content, advice_json=excluded.advice_json,
                    model_name=excluded.model_name,
                    created_at=excluded.created_at""",
                (field_id, acquisition_id, content, advice_json, model_name, now),
            )
        recommendation = self.get_recommendation(field_id)
        assert recommendation is not None
        return recommendation

    def get_recommendation(self, field_id: int) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM recommendations WHERE field_id = ?", (field_id,)
            ).fetchone()
        if row is None:
            return None
        return decode_json_columns(row_to_dict(row), "advice_json")

    def index_value_records(
        self,
        field_id: int,
        *,
        year: int | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
        limit: int | None = MAX_STORED_ACQUISITIONS,
    ) -> list[dict[str, Any]]:
        conditions = ["field_id = ?"]
        parameters: list[Any] = [field_id]
        if year is not None:
            conditions.append("substr(acquired_at, 1, 4) = ?")
            parameters.append(str(year))
        if from_date is not None:
            conditions.append("substr(acquired_at, 1, 10) >= ?")
            parameters.append(from_date.isoformat())
        if to_date is not None:
            conditions.append("substr(acquired_at, 1, 10) <= ?")
            parameters.append(to_date.isoformat())

        with self.database.connect() as connection:
            acquisition_sql = (
                f"SELECT id FROM acquisitions WHERE {' AND '.join(conditions)} "
                "ORDER BY acquired_at DESC, id DESC"
            )
            acquisition_parameters = list(parameters)
            if limit is not None:
                acquisition_sql += " LIMIT ?"
                acquisition_parameters.append(limit)
            acquisition_rows = connection.execute(
                acquisition_sql, acquisition_parameters
            ).fetchall()
            acquisition_ids = [int(row["id"]) for row in acquisition_rows]
            if not acquisition_ids:
                return []

            acquisition_placeholders = ",".join("?" for _ in acquisition_ids)
            placeholders = ",".join("?" for _ in IMPORTANT_INDEXES)
            rows = connection.execute(
                f"""SELECT a.id AS acquisition_id, a.acquired_at, a.product_id,
                a.cloud_coverage, a.fully_cloudy, v.index_name, v.relative_path,
                v.valid_pixel_count, v.mean_value, v.min_value, v.median_value,
                v.max_value
                FROM acquisitions a JOIN index_values v ON v.acquisition_id = a.id
                WHERE a.id IN ({acquisition_placeholders})
                AND v.index_name IN ({placeholders})
                ORDER BY a.acquired_at, v.index_name""",
                (*acquisition_ids, *IMPORTANT_INDEXES),
            ).fetchall()
        return [row_to_dict(row) for row in rows]

    def prune_old_image_data(
        self, field_id: int, *, keep: int = MAX_STORED_ACQUISITIONS
    ) -> list[str]:
        with self.database.connect() as connection:
            old_rows = connection.execute(
                """SELECT id FROM acquisitions WHERE field_id = ? AND id NOT IN (
                    SELECT id FROM acquisitions WHERE field_id = ?
                    ORDER BY acquired_at DESC, id DESC LIMIT ?
                )""",
                (field_id, field_id, keep),
            ).fetchall()
            old_ids = [int(row["id"]) for row in old_rows]
            if not old_ids:
                return []
            placeholders = ",".join("?" for _ in old_ids)
            artifact_rows = connection.execute(
                f"SELECT relative_path FROM artifacts WHERE acquisition_id IN ({placeholders})",
                old_ids,
            ).fetchall()
            connection.execute(
                f"DELETE FROM artifacts WHERE acquisition_id IN ({placeholders})", old_ids
            )
        # Faqat rasm artefaktlari (PNG) o'chiriladi; kuzatuv va index_values
        # yozuvlari (statistikalar bilan) sana-oralig'i grafiklari uchun saqlanadi.
        return [str(row["relative_path"]) for row in artifact_rows]

    # --- Chat Messages & Summary ---
    def add_chat_message(
        self,
        field_id: int,
        role: str,
        content: str,
        rag_sources: list[dict[str, Any]] | None = None,
        rag_strategy: str | None = None,
        rag_source_title: str | None = None,
    ) -> dict[str, Any]:
        now = iso_utc()
        rag_sources_json = json.dumps(rag_sources, ensure_ascii=False) if rag_sources else None
        with self.database.connect() as connection:
            cursor = connection.execute(
                """INSERT INTO field_chat_messages(field_id, role, content, rag_sources_json, rag_strategy, rag_source_title, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (field_id, role, content, rag_sources_json, rag_strategy, rag_source_title, now),
            )
            msg_id = int(cursor.lastrowid or 0)
            row = connection.execute(
                "SELECT * FROM field_chat_messages WHERE id = ?", (msg_id,)
            ).fetchone()
        assert row is not None
        return decode_json_columns(row_to_dict(row), "rag_sources_json")

    def list_chat_messages(self, field_id: int, limit: int = 50) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """SELECT * FROM field_chat_messages
                WHERE field_id = ?
                ORDER BY id ASC LIMIT ?""",
                (field_id, limit),
            ).fetchall()
        return [decode_json_columns(row_to_dict(row), "rag_sources_json") for row in rows]

    def get_chat_summary(self, field_id: int) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM field_chat_summaries WHERE field_id = ?", (field_id,)
            ).fetchone()
        if row is None:
            return None
        return row_to_dict(row)

    def upsert_chat_summary(
        self,
        field_id: int,
        summary_text: str,
        message_count: int,
        last_message_id: int,
    ) -> dict[str, Any]:
        now = iso_utc()
        with self.database.connect() as connection:
            connection.execute(
                """INSERT INTO field_chat_summaries(field_id, summary_text, message_count, last_message_id, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(field_id) DO UPDATE SET
                    summary_text=excluded.summary_text,
                    message_count=excluded.message_count,
                    last_message_id=excluded.last_message_id,
                    updated_at=excluded.updated_at""",
                (field_id, summary_text, message_count, last_message_id, now),
            )
        summary = self.get_chat_summary(field_id)
        assert summary is not None
        return summary

    # --- RAG Documents ---
    def list_rag_documents(self) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM rag_documents ORDER BY created_at DESC"
            ).fetchall()
        return [row_to_dict(row) for row in rows]

    def get_rag_document(self, document_id: int) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM rag_documents WHERE id = ?", (document_id,)
            ).fetchone()
        return row_to_dict(row) if row else None

    def toggle_rag_document(self, document_id: int, is_active: bool) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            connection.execute(
                "UPDATE rag_documents SET is_active = ? WHERE id = ?",
                (int(is_active), document_id),
            )
            row = connection.execute(
                "SELECT * FROM rag_documents WHERE id = ?", (document_id,)
            ).fetchone()
        return row_to_dict(row) if row else None

    def get_active_rag_document_ids(self) -> list[int]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT id FROM rag_documents WHERE is_active = 1"
            ).fetchall()
        return [int(row["id"]) for row in rows]

    def delete_rag_document(self, document_id: int) -> bool:
        with self.database.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM rag_documents WHERE id = ?", (document_id,)
            )
            return cursor.rowcount > 0


    # --- Yield Predictions ---
    def save_yield_prediction(
        self,
        *,
        field_id: int,
        crop: str,
        model_name: str,
        predicted_yield_t_ha: float,
        yield_min_expected: float,
        yield_max_expected: float,
        total_expected_yield_tons: float,
        field_area_ha: float,
        top_features: list[dict[str, Any]],
        phenology_timeline: list[dict[str, Any]],
    ) -> dict[str, Any]:
        now = iso_utc()
        with self.database.connect() as connection:
            cursor = connection.execute(
                """INSERT INTO yield_predictions(
                    field_id, crop, model_name, predicted_yield_t_ha, yield_min_expected,
                    yield_max_expected, total_expected_yield_tons, field_area_ha,
                    top_features_json, phenology_timeline_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    field_id,
                    crop,
                    model_name,
                    predicted_yield_t_ha,
                    yield_min_expected,
                    yield_max_expected,
                    total_expected_yield_tons,
                    field_area_ha,
                    json.dumps(top_features, ensure_ascii=False),
                    json.dumps(phenology_timeline, ensure_ascii=False),
                    now,
                ),
            )
            rec_id = int(cursor.lastrowid or 0)
            row = connection.execute(
                "SELECT * FROM yield_predictions WHERE id = ?", (rec_id,)
            ).fetchone()
        assert row is not None
        return decode_json_columns(
            row_to_dict(row), "top_features_json", "phenology_timeline_json"
        )

    def get_latest_yield_prediction(self, field_id: int) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """SELECT * FROM yield_predictions
                WHERE field_id = ?
                ORDER BY created_at DESC, id DESC LIMIT 1""",
                (field_id,),
            ).fetchone()
        if row is None:
            return None
        return decode_json_columns(
            row_to_dict(row), "top_features_json", "phenology_timeline_json"
        )