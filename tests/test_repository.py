import sqlite3

from app.constants import INDEX_NAMES
from app.db import Database
from app.indices import IndexStats


def test_product_revision_idempotency_and_only_new_data(repository) -> None:
    args = dict(
        acquired_at="2026-05-01T10:00:00Z",
        product_id="P1",
        revision_key="R1",
        cloud_coverage=10.0,
        metadata={},
    )
    first, created = repository.create_acquisition_if_new(1, **args)
    duplicate, created_again = repository.create_acquisition_if_new(1, **args)
    revised, revised_created = repository.create_acquisition_if_new(
        1, **{**args, "revision_key": "R2"}
    )
    assert created and not created_again and revised_created
    assert first["id"] == duplicate["id"]
    assert revised["id"] != first["id"]


def test_index_paths_and_structured_recommendation_atomic_replace(repository) -> None:
    with repository.database.connect() as connection:
        tables = {
            row["name"]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert "index_stats" not in tables
    acquisition, _ = repository.create_acquisition_if_new(
        1,
        acquired_at="2026-05-01T10:00:00Z",
        product_id="P1",
        revision_key="R1",
        cloud_coverage=100.0,
        metadata={},
    )
    repository.complete_acquisition(
        acquisition["id"],
        {
            name: (f"values/{name}.npy", IndexStats(None, None, None, None, 0))
            for name in INDEX_NAMES
        },
        processed_at="2026-05-01T11:00:00Z",
    )
    current = repository.get_acquisition(1, acquisition["id"])
    assert current["fully_cloudy"] is True
    first = repository.replace_recommendation(
        1, acquisition["id"], "old", "gpt-5.4-nano", {"red": ["A"], "yellow": [], "green": []}
    )
    second = repository.replace_recommendation(
        1, acquisition["id"], "new", "gpt-5.4-mini", {"red": [], "yellow": [], "green": ["B"]}
    )
    assert first["content"] == "old" and second["content"] == "new"
    assert second["advice"] == {"red": [], "yellow": [], "green": ["B"]}
    assert repository.has_complete_index_values(acquisition["id"])


def test_v1_database_migrates_away_from_persisted_statistics(tmp_path) -> None:
    path = tmp_path / "v1.sqlite3"
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE index_stats (acquisition_id INTEGER, index_name TEXT);
        CREATE TABLE recommendations (
            field_id INTEGER PRIMARY KEY,
            acquisition_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            model_name TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """
    )
    connection.close()

    database = Database(path)
    database.initialize()
    with database.connect() as migrated:
        tables = {
            row["name"]
            for row in migrated.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        columns = {row["name"] for row in migrated.execute("PRAGMA table_info(recommendations)")}
    assert "index_stats" not in tables
    assert "index_values" in tables
    assert "advice_json" in columns
