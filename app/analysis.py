import logging
from dataclasses import dataclass
from datetime import date
from typing import Any

from app.ai import AIClient, AIError
from app.constants import INDEX_NAMES, RENDER_VERSION
from app.indices import IndexStats, calculate_indices, calculate_stats
from app.rendering import ArtifactWriter, render_heatmap, render_qa, render_rgb
from app.repository import Repository
from app.sentinel import CatalogItem, SentinelHubClient, valid_pixel_mask
from app.timeutils import iso_utc

logger = logging.getLogger(__name__)


def _round2(value: float | None) -> float | None:
    """AI ga uzatiladigan son qiymatlarini 2 kasr xonagacha yaxlitlash."""
    return round(float(value), 2) if value is not None else None


class AnalysisError(RuntimeError):
    pass


@dataclass(frozen=True)
class AnalysisResult:
    selected_acquisition: dict[str, Any]
    new_acquisitions_processed: int
    recommendation: dict[str, Any] | None
    recommendation_error: str | None


@dataclass(frozen=True)
class HistoricalLoadResult:
    acquisitions_found: int
    new_acquisitions_processed: int


class AnalysisService:
    def __init__(
        self,
        repository: Repository,
        sentinel: SentinelHubClient,
        artifacts: ArtifactWriter,
        ai: AIClient | None,
        cloud_free_threshold: float,
    ) -> None:
        self.repository = repository
        self.sentinel = sentinel
        self.artifacts = artifacts
        self.ai = ai
        self.cloud_free_threshold = cloud_free_threshold

    async def _process_item(
        self,
        field: dict[str, Any],
        item: CatalogItem,
        acquisition: dict[str, Any],
        *,
        render_artifacts: bool = True,
    ) -> None:
        acquisition_id = int(acquisition["id"])
        logger.info(
            "Acquisition processing started field_id=%s acquisition_id=%s product_id=%s",
            field["id"],
            acquisition_id,
            item.product_id,
        )
        try:
            raster = await self.sentinel.raster(field["geometry"], item.acquired_at)
            valid = valid_pixel_mask(raster)
            index_values = calculate_indices(raster.bands, valid)
            created_at = iso_utc()
            layer_count = 0
            if render_artifacts:
                layer_images = {"RGB": render_rgb(raster), "QA": render_qa(raster)}
                layer_images.update(
                    {name: render_heatmap(index_values[name], valid) for name in INDEX_NAMES}
                )
                for layer_name, image in layer_images.items():
                    relative = self.artifacts.relative_path(
                        int(field["id"]), item.product_id, item.revision_key, layer_name
                    )
                    self.artifacts.write_atomic(relative, image)
                    self.repository.upsert_artifact(
                        acquisition_id=acquisition_id,
                        layer_name=layer_name,
                        bbox=raster.bbox,
                        width=raster.width,
                        height=raster.height,
                        render_version=RENDER_VERSION,
                        relative_path=relative.as_posix(),
                        created_at=created_at,
                    )
                layer_count = len(layer_images)
            index_data: dict[str, tuple[str, IndexStats]] = {}
            for name in INDEX_NAMES:
                relative = self.artifacts.values_relative_path(
                    int(field["id"]), item.product_id, item.revision_key, name
                )
                # To'liq raster massivini (.npy) diskka yozmaymiz: grafik va AI
                # tarixi uchun zarur statistikalar bazada saqlanadi. Bu yillik
                # ma'lumot yuklanganda xotira va disk hajmini sezilarli kamaytiradi.
                index_data[name] = (relative.as_posix(), calculate_stats(index_values[name]))
            self.repository.complete_acquisition(
                acquisition_id, index_data, processed_at=created_at
            )
            logger.info(
                "Acquisition processing completed field_id=%s acquisition_id=%s "
                "layers=%d metrics=%d",
                field["id"],
                acquisition_id,
                layer_count,
                len(index_data),
            )
        except Exception as exc:
            self.repository.mark_processing_failure(acquisition_id, str(exc))
            logger.exception("Acquisition processing failed acquisition_id=%s", acquisition_id)
            raise

    def _record_stats(self, record: dict[str, Any]) -> IndexStats:
        """Bazadagi statistikani o'qish; migratsiyadan oldingi yozuvlar uchun
        .npy fayldan hisoblab olishga qaytish (fallback)."""
        valid_pixel_count = int(record["valid_pixel_count"])
        if record["mean_value"] is not None or valid_pixel_count == 0:
            return IndexStats(
                minimum=record["min_value"],
                mean=record["mean_value"],
                median=record["median_value"],
                maximum=record["max_value"],
                valid_pixel_count=valid_pixel_count,
            )
        try:
            values = self.artifacts.read_values(str(record["relative_path"]))
        except FileNotFoundError:
            return IndexStats(None, None, None, None, valid_pixel_count)
        return calculate_stats(values)

    def _metric_history(self, field_id: int) -> dict[str, list[dict[str, Any]]]:
        history: dict[str, list[dict[str, Any]]] = {name: [] for name in INDEX_NAMES}
        for record in self.repository.index_value_records(field_id, limit=5):
            stats = self._record_stats(record)
            history[str(record["index_name"])].append(
                {
                    "acquired_at": record["acquired_at"],
                    "product_id": record["product_id"],
                    "cloud_coverage": _round2(record["cloud_coverage"]),
                    "minimum": _round2(stats.minimum),
                    "mean": _round2(stats.mean),
                    "median": _round2(stats.median),
                    "maximum": _round2(stats.maximum),
                }
            )
        logger.info(
            "AI statistics calculated on demand field_id=%s metrics=%d", field_id, len(history)
        )
        return history

    async def analyze(self, field_id: int, mode: str) -> AnalysisResult:
        logger.info("Field analysis started field_id=%s mode=%s", field_id, mode)
        field = self.repository.get_field(field_id)
        catalog_items = await self.sentinel.catalog(field["geometry"])
        processed: list[dict[str, Any]] = []
        for item in catalog_items:
            acquisition, created = self.repository.create_acquisition_if_new(
                field_id,
                acquired_at=item.acquired_at,
                product_id=item.product_id,
                revision_key=item.revision_key,
                cloud_coverage=item.cloud_coverage,
                metadata=item.metadata,
            )
            if (
                created
                or acquisition["processed_at"] is None
                or not self.repository.has_complete_index_values(int(acquisition["id"]))
                or not self.repository.has_complete_artifacts(int(acquisition["id"]))
            ):
                await self._process_item(field, item, acquisition)
                processed.append(self.repository.get_acquisition(field_id, int(acquisition["id"])))
        removed_paths = self.repository.prune_old_image_data(field_id)
        for relative_path in removed_paths:
            self.artifacts.delete_relative(relative_path)
        if removed_paths:
            logger.info(
                "Old image data pruned field_id=%s removed_files=%d", field_id, len(removed_paths)
            )
        threshold = self.cloud_free_threshold if mode == "latest_cloud_free" else None
        selected = self.repository.select_acquisition(field_id, cloud_free_threshold=threshold)
        if selected is None:
            if mode == "latest_cloud_free":
                raise AnalysisError(
                    f"Cloud coverage {self.cloud_free_threshold:g}% chegarasiga mos "
                    "tasvir topilmadi"
                )
            raise AnalysisError("Sentinel-2 ning oxirgi 5 ta kuzatuvi topilmadi")

        recommendation = self.repository.get_recommendation(field_id)
        recommendation_error: str | None = None
        if processed:
            newest = max(processed, key=lambda value: value["acquired_at"])
            if self.ai is None:
                recommendation_error = "OPENAI_API_KEY sozlanmagan; avvalgi tavsiya saqlandi"
            else:
                try:
                    ai_result = await self.ai.recommendation(
                        field, newest, self._metric_history(field_id)
                    )
                    recommendation = self.repository.replace_recommendation(
                        field_id,
                        int(newest["id"]),
                        ai_result.content,
                        ai_result.model_name,
                        ai_result.advice,
                    )
                except AIError as exc:
                    recommendation_error = str(exc)
        logger.info(
            "Field analysis completed field_id=%s processed=%d selected_id=%s advice_updated=%s",
            field_id,
            len(processed),
            selected["id"],
            bool(processed and recommendation_error is None and self.ai is not None),
        )
        return AnalysisResult(selected, len(processed), recommendation, recommendation_error)

    async def load_history(self, field_id: int, from_date: date) -> HistoricalLoadResult:
        """Cache metric arrays for every catalog acquisition in a requested date range."""
        logger.info("Historical metric load started field_id=%s from_date=%s", field_id, from_date)
        field = self.repository.get_field(field_id)
        catalog_items = await self.sentinel.catalog_range(field["geometry"], from_date)
        processed_count = 0
        for item in catalog_items:
            acquisition, created = self.repository.create_acquisition_if_new(
                field_id,
                acquired_at=item.acquired_at,
                product_id=item.product_id,
                revision_key=item.revision_key,
                cloud_coverage=item.cloud_coverage,
                metadata=item.metadata,
            )
            if (
                created
                or acquisition["processed_at"] is None
                or not self.repository.has_complete_index_values(int(acquisition["id"]))
            ):
                await self._process_item(field, item, acquisition, render_artifacts=False)
                processed_count += 1
        logger.info(
            "Historical metric load completed field_id=%s found=%d processed=%d",
            field_id,
            len(catalog_items),
            processed_count,
        )
        return HistoricalLoadResult(len(catalog_items), processed_count)
