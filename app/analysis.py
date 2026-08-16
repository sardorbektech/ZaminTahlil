import asyncio
import logging
from dataclasses import dataclass
from datetime import date
from typing import Any

from app.ai import AIClient, AIError
from app.constants import INDEX_NAMES, RENDER_VERSION
from app.indices import IndexStats, calculate_indices, calculate_stats
from app.rendering import ArtifactWriter, render_heatmap, render_qa, render_rgb
from app.repository import Repository
from app.sentinel import CatalogItem, RasterData, SentinelHubClient, valid_pixel_mask
from app.timeutils import iso_utc

logger = logging.getLogger(__name__)

# Sentinel Hub rate limit'ga rioya etgan holda parallel yuklash.
RASTER_FETCH_CONCURRENCY = 3


def _round2(value: float | None) -> float | None:
    """AI ga uzatiladigan son qiymatlarini 2 kasr xonagacha yaxlitlash."""
    return round(float(value), 2) if value is not None else None


def _extract_metric_mean(val_list: Any, default: float) -> float:
    if not val_list or not isinstance(val_list, list):
        return default
    last = val_list[-1]
    if isinstance(last, dict):
        m = last.get("mean") or last.get("mean_value") or last.get("median")
        if m is not None:
            try:
                return float(m)
            except (ValueError, TypeError):
                return default
    elif isinstance(last, int | float):
        return float(last)
    return default


def generate_expert_agronomy_advice(
    crop_name: str, metric_history: dict[str, Any]
) -> tuple[str, dict[str, list[str]]]:
    latest_ndvi = _extract_metric_mean(metric_history.get("NDVI"), 0.45)
    latest_ndmi = _extract_metric_mean(metric_history.get("NDMI"), 0.25)
    latest_ndre = _extract_metric_mean(metric_history.get("NDRE"), 0.28)

    red: list[str] = []
    yellow: list[str] = []
    green: list[str] = []

    if latest_ndvi < 0.35:
        red.append(f"{crop_name} maydonida vegetatsiya (NDVI: {latest_ndvi:.2f}) past darajada. Sug'orish va oziqlantirish zarur.")
    elif latest_ndvi < 0.55:
        yellow.append(f"O'rtacha vegetatsiya holati (NDVI: {latest_ndvi:.2f}). Bargdan mikroelementlar bilan oziqlantirish tavsiya etiladi.")
    else:
        green.append(f"Vegetatsiya ko'rsatkichi (NDVI: {latest_ndvi:.2f}) yuqori va me'yorda rivojlanmoqda.")

    if latest_ndmi < 0.15:
        red.append("Barg namligi (NDMI) past. Tuproqda namlik yetishmovchiligi xavfi mavjud.")
    elif latest_ndmi < 0.30:
        yellow.append("Tuproq va o'simlik namligi o'rtacha. Navbatdagi sug'orish muddatini rejalashtiring.")
    else:
        green.append("O'simlik to'qimalarida suv ta'minoti yetarli darajada.")

    if latest_ndre < 0.20:
        yellow.append("Xlorofill (NDRE) miqdori kamaygan, azotli o'g'it kiritishni ko'rib chiqing.")
    else:
        green.append("Xlorofill va azot balansi ijobiy dinamikada.")

    advice = {"red": red[:3], "yellow": yellow[:3], "green": green[:3]}
    content = f"{crop_name} maydoni bo'yicha sun'iy yo'ldosh tahlili asosida agronomik xulosa shakllantirildi."
    return content, advice




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
        raster: RasterData,
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

    async def _fetch_rasters(
        self, field: dict[str, Any], items: list[CatalogItem]
    ) -> list[RasterData | Exception]:
        """Katalog elementlari rasterlarini cheklangan parallelikda yuklash.

        Xatolar istisno obyekti sifatida qaytariladi — chaqiruvchi ularni
        ketma-ket qayta ishlash bosqichida ko'taradi.
        """
        semaphore = asyncio.Semaphore(RASTER_FETCH_CONCURRENCY)

        async def fetch(item: CatalogItem) -> RasterData | Exception:
            async with semaphore:
                try:
                    return await self.sentinel.raster(field["geometry"], item.acquired_at)
                except Exception as exc:  # noqa: BLE001 - xato natija sifatida uzatiladi
                    return exc

        return list(await asyncio.gather(*(fetch(item) for item in items)))

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
        pending: list[tuple[CatalogItem, dict[str, Any]]] = []
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
                pending.append((item, acquisition))
        rasters = await self._fetch_rasters(field, [item for item, _ in pending])
        for (item, acquisition), raster in zip(pending, rasters, strict=True):
            if isinstance(raster, Exception):
                self.repository.mark_processing_failure(int(acquisition["id"]), str(raster))
                logger.error(
                    "Acquisition raster fetch failed acquisition_id=%s: %s",
                    acquisition["id"],
                    raster,
                )
                raise raster
            await self._process_item(field, item, acquisition, raster=raster)
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
                if recommendation is None:
                    crop = str(field.get("crop_name") or "Ekin")
                    content, advice = generate_expert_agronomy_advice(crop, self._metric_history(field_id))
                    recommendation = self.repository.replace_recommendation(
                        field_id,
                        int(newest["id"]),
                        content,
                        "expert-agronomy-rules",
                        advice,
                    )
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
                    if recommendation is None:
                        crop = str(field.get("crop_name") or "Ekin")
                        content, advice = generate_expert_agronomy_advice(crop, self._metric_history(field_id))
                        recommendation = self.repository.replace_recommendation(
                            field_id,
                            int(newest["id"]),
                            content,
                            "expert-agronomy-rules",
                            advice,
                        )
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
        pending: list[tuple[CatalogItem, dict[str, Any]]] = []
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
                pending.append((item, acquisition))
        rasters = await self._fetch_rasters(field, [item for item, _ in pending])
        for (item, acquisition), raster in zip(pending, rasters, strict=True):
            if isinstance(raster, Exception):
                self.repository.mark_processing_failure(int(acquisition["id"]), str(raster))
                logger.error(
                    "Acquisition raster fetch failed acquisition_id=%s: %s",
                    acquisition["id"],
                    raster,
                )
                raise raster
            await self._process_item(field, item, acquisition, raster=raster, render_artifacts=False)
            processed_count += 1
        logger.info(
            "Historical metric load completed field_id=%s found=%d processed=%d",
            field_id,
            len(catalog_items),
            processed_count,
        )
        return HistoricalLoadResult(len(catalog_items), processed_count)
