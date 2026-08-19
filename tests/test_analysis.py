from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from app.ai import AIError, AIResult
from app.analysis import AnalysisService
from app.rendering import ArtifactWriter
from app.sentinel import CatalogItem, RasterData


class FakeSentinel:
    def __init__(self) -> None:
        self.items = [CatalogItem("2026-05-01T10:00:00Z", "P1", "R1", 10.0, {"catalog_id": "P1"})]
        self.raster_calls = 0

    async def catalog(self, geometry: dict[str, Any]) -> list[CatalogItem]:
        return self.items

    async def catalog_range(self, geometry: dict[str, Any], from_date: date) -> list[CatalogItem]:
        return [item for item in self.items if item.acquired_at[:10] >= from_date.isoformat()]

    async def raster(self, geometry: dict[str, Any], acquired_at: str) -> RasterData:
        self.raster_calls += 1
        cloudy = acquired_at.startswith("2026-05-07")
        values = {
            name: np.full((2, 2), 0.2 + index / 100, dtype=np.float32)
            for index, name in enumerate(("B02", "B03", "B04", "B05", "B08", "B8A", "B11"))
        }
        return RasterData(
            values,
            np.full((2, 2), 9 if cloudy else 4, dtype=np.uint8),
            np.ones((2, 2), dtype=bool),
            [69.2, 41.2, 69.21, 41.21],
            2,
            2,
        )


class FakeAI:
    def __init__(self) -> None:
        self.calls = 0
        self.fail = False
        self.history = None

    async def recommendation(self, field, acquisition, history, *args, **kwargs) -> AIResult:
        self.calls += 1
        self.history = history
        if self.fail:
            raise AIError("AI unavailable")
        return AIResult(f"recommendation-{self.calls}", "gpt-5.4-nano")



@pytest.mark.asyncio
async def test_incremental_processing_cache_cloudy_update_and_atomic_failure(
    repository, tmp_path: Path
) -> None:
    sentinel = FakeSentinel()
    ai = FakeAI()
    service = AnalysisService(repository, sentinel, ArtifactWriter(tmp_path / "artifacts"), ai, 20)

    first = await service.analyze(1, "latest")
    repeated = await service.analyze(1, "latest")
    assert first.new_acquisitions_processed == 1
    assert repeated.new_acquisitions_processed == 0
    assert sentinel.raster_calls == 1 and ai.calls == 1
    artifacts = repository.list_artifacts(1, first.selected_acquisition["id"])
    assert len(artifacts) == 7
    assert {item["layer_name"] for item in artifacts} == {
        "RGB",
        "NDVI",
        "NDMI",
        "NDRE",
        "EVI",
        "BSI",
        "QA",
    }
    assert len({tuple(item["bbox"]) for item in artifacts}) == 1
    assert len({(item["width"], item["height"]) for item in artifacts}) == 1
    assert len({item["render_version"] for item in artifacts}) == 1

    sentinel.items.append(
        CatalogItem("2026-05-07T10:00:00Z", "P2", "R1", 100.0, {"catalog_id": "P2"})
    )
    cloudy = await service.analyze(1, "latest")
    assert cloudy.selected_acquisition["fully_cloudy"] is True
    assert cloudy.selected_acquisition["valid_pixel_count"] == 0
    assert all(item[-1]["mean"] is None for item in ai.history.values())
    cloud_free = await service.analyze(1, "latest_cloud_free")
    assert cloud_free.selected_acquisition["product_id"] == "P1"

    current = repository.get_recommendation(1)
    ai.fail = True
    sentinel.items.append(
        CatalogItem("2026-05-13T10:00:00Z", "P3", "R1", 12.0, {"catalog_id": "P3"})
    )
    failed = await service.analyze(1, "latest")
    assert failed.recommendation_error == "AI unavailable"
    assert repository.get_recommendation(1) == current


@pytest.mark.asyncio
async def test_only_latest_five_acquisitions_keep_image_data(repository, tmp_path: Path) -> None:
    sentinel = FakeSentinel()
    sentinel.items = [
        CatalogItem(
            f"2026-05-{day:02d}T10:00:00Z", f"P{day}", "R1", 10.0, {"catalog_id": f"P{day}"}
        )
        for day in range(1, 7)
    ]
    service = AnalysisService(
        repository, sentinel, ArtifactWriter(tmp_path / "artifacts"), None, 20
    )
    await service.analyze(1, "latest")
    acquisitions = repository.list_acquisitions(1)
    assert len(acquisitions) == 5
    assert {item["product_id"] for item in acquisitions} == {"P2", "P3", "P4", "P5", "P6"}


@pytest.mark.asyncio
async def test_historical_load_keeps_all_metrics_but_latest_five_images(
    repository, tmp_path: Path
) -> None:
    sentinel = FakeSentinel()
    sentinel.items = [
        CatalogItem(
            f"2025-03-{day:02d}T10:00:00Z",
            f"P{day}",
            "R1",
            10.0,
            {"catalog_id": f"P{day}"},
        )
        for day in range(1, 7)
    ]
    service = AnalysisService(
        repository, sentinel, ArtifactWriter(tmp_path / "artifacts"), None, 20
    )

    loaded = await service.load_history(1, date(2025, 3, 1))
    repeated = await service.load_history(1, date(2025, 3, 1))
    assert loaded.acquisitions_found == 6
    assert loaded.new_acquisitions_processed == 6
    assert repeated.new_acquisitions_processed == 0
    assert len(repository.index_value_records(1, from_date=date(2025, 3, 1), limit=None)) == 30
    assert repository.list_acquisitions(1) == []

    await service.analyze(1, "latest")
    assert len(repository.list_acquisitions(1)) == 5
    assert len(repository.index_value_records(1, from_date=date(2025, 3, 1), limit=None)) == 30
