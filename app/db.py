import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 3

SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fields (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    geometry_json TEXT NOT NULL,
    geometry_hash TEXT NOT NULL UNIQUE,
    area_hectares REAL NOT NULL CHECK(area_hectares > 0),
    crop_name TEXT NOT NULL CHECK(length(crop_name) BETWEEN 1 AND 120),
    planted_on TEXT NOT NULL,
    growth_stage TEXT NOT NULL CHECK(length(growth_stage) BETWEEN 1 AND 120),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS acquisitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    field_id INTEGER NOT NULL REFERENCES fields(id) ON DELETE CASCADE,
    acquired_at TEXT NOT NULL,
    product_id TEXT NOT NULL,
    revision_key TEXT NOT NULL,
    cloud_coverage REAL CHECK(cloud_coverage IS NULL OR cloud_coverage BETWEEN 0 AND 100),
    processed_at TEXT,
    source_metadata_json TEXT NOT NULL,
    valid_pixel_count INTEGER,
    fully_cloudy INTEGER NOT NULL DEFAULT 0 CHECK(fully_cloudy IN (0, 1)),
    processing_error TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(field_id, product_id, revision_key)
);
CREATE INDEX IF NOT EXISTS idx_acquisitions_field_time
ON acquisitions(field_id, acquired_at DESC);

CREATE TABLE IF NOT EXISTS index_values (
    acquisition_id INTEGER NOT NULL REFERENCES acquisitions(id) ON DELETE CASCADE,
    index_name TEXT NOT NULL,
    relative_path TEXT NOT NULL UNIQUE,
    valid_pixel_count INTEGER NOT NULL CHECK(valid_pixel_count >= 0),
    -- Grafik va AI tarixi uchun oldindan hisoblangan statistikalar. Bu qiymatlar
    -- to'liq raster massivini (.npy) qayta o'qishni keraksiz qiladi va yillik
    -- ma'lumot uchun xotira/diskdan tejaydi. Yaroqli piksel bo'lmasa NULL bo'ladi.
    mean_value REAL,
    min_value REAL,
    median_value REAL,
    max_value REAL,
    PRIMARY KEY(acquisition_id, index_name)
);

CREATE TABLE IF NOT EXISTS artifacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    acquisition_id INTEGER NOT NULL REFERENCES acquisitions(id) ON DELETE CASCADE,
    layer_name TEXT NOT NULL,
    bbox_json TEXT NOT NULL,
    width INTEGER NOT NULL CHECK(width > 0),
    height INTEGER NOT NULL CHECK(height > 0),
    render_version TEXT NOT NULL,
    relative_path TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    UNIQUE(acquisition_id, layer_name, render_version)
);

CREATE TABLE IF NOT EXISTS recommendations (
    field_id INTEGER PRIMARY KEY REFERENCES fields(id) ON DELETE CASCADE,
    acquisition_id INTEGER NOT NULL REFERENCES acquisitions(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    advice_json TEXT NOT NULL DEFAULT '{"red":[],"yellow":[],"green":[]}',
    model_name TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(SCHEMA)
            recommendation_columns = {
                str(row["name"])
                for row in connection.execute("PRAGMA table_info(recommendations)").fetchall()
            }
            if "advice_json" not in recommendation_columns:
                connection.execute(
                    "ALTER TABLE recommendations ADD COLUMN advice_json TEXT NOT NULL "
                    'DEFAULT \'{"red":[],"yellow":[],"green":[]}\''
                )
            index_value_columns = {
                str(row["name"])
                for row in connection.execute("PRAGMA table_info(index_values)").fetchall()
            }
            for stat_column in ("mean_value", "min_value", "median_value", "max_value"):
                if stat_column not in index_value_columns:
                    connection.execute(
                        f"ALTER TABLE index_values ADD COLUMN {stat_column} REAL"
                    )
            connection.execute("DROP TABLE IF EXISTS index_stats")
            allowed = ("NDVI", "NDMI", "NDRE", "EVI", "BSI")
            placeholders = ",".join("?" for _ in allowed)
            connection.execute(
                f"DELETE FROM artifacts WHERE layer_name NOT IN ('RGB','QA',{placeholders})",
                allowed,
            )
            connection.execute(
                "INSERT OR IGNORE INTO schema_version(version, applied_at) "
                "VALUES (?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))",
                (SCHEMA_VERSION,),
            )

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)


def decode_json_columns(record: dict[str, Any], *columns: str) -> dict[str, Any]:
    for column in columns:
        value = record.get(column)
        if isinstance(value, str):
            record[column.removesuffix("_json")] = json.loads(value)
            del record[column]
    return record
