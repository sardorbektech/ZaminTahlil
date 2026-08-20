import asyncio
import logging
import numpy as np
from dataclasses import dataclass
from datetime import date
from typing import Any

from app.ai import AIClient, AIError
from app.anomaly import AnomalyAnalysisReport, detect_and_cluster_anomalies
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
    crop_name: str,
    metric_history: dict[str, Any],
    *,
    anomaly_report: AnomalyAnalysisReport | None = None,
) -> tuple[str, dict[str, list[str]]]:
    red: list[str] = []
    yellow: list[str] = []
    green: list[str] = []

    latest_ndvi = _extract_metric_mean(metric_history.get("NDVI"), 0.45)
    latest_ndmi = _extract_metric_mean(metric_history.get("NDMI"), 0.25)
    latest_ndre = _extract_metric_mean(metric_history.get("NDRE"), 0.28)

    if anomaly_report and anomaly_report.top_clusters:
        for idx, cluster in enumerate(anomaly_report.top_clusters, 1):
            if cluster.risk_level in ("CRITICAL", "HIGH"):
                detail_msg = (
                    f"⚠️ O'choq #{idx} ({cluster.compass_sector} sektor, {cluster.area_ha:.2f} ga, "
                    f"E={cluster.e_anisotropy:.1f} {cluster.orientation_label}): "
                    f"{cluster.diagnosis_title}. "
                )
                if cluster.pathogen_name:
                    detail_msg += f"Ehtimoliy patogen: {cluster.pathogen_name}. "
                detail_msg += f"Tavsiya: {cluster.recommended_treatment} {cluster.agrotechnical_action}"
                red.append(detail_msg)
            elif cluster.risk_level == "MODERATE":
                mod_msg = (
                    f"🟡 O'choq #{idx} ({cluster.compass_sector} sektor, {cluster.area_ha:.2f} ga, "
                    f"E={cluster.e_anisotropy:.1f}): {cluster.diagnosis_title}. "
                    f"Tavsiya: {cluster.recommended_treatment}"
                )
                yellow.append(mod_msg)

    # Qo'shimcha/umumiy holat tekshiruvlari
    if not red:
        if latest_ndvi < 0.35:
            red.append(f"{crop_name} maydonida vegetatsiya (NDVI: {latest_ndvi:.2f}) past darajada. Sug'orish va oziqlantirish zarur.")
        elif latest_ndmi < 0.15:
            red.append("Barg namligi (NDMI) o'ta past. Tuproqda namlik yetishmovchiligi va gidrostress xavfi mavjud.")

    if not yellow:
        if latest_ndre < 0.25:
            yellow.append(f"Xlorofill va azot (NDRE: {latest_ndre:.2f}) past. Karbamid (15-20 kg/ga) yoki bargdan mikroelementlar berish tavsiya etiladi.")
        elif latest_ndvi < 0.55:
            yellow.append(f"O'rtacha vegetatsiya holati (NDVI: {latest_ndvi:.2f}). O'sishni rag'batlantiruvchi biostimulyatorlar bilan ishlov bering.")

    # Ijobiy zonalar
    if latest_ndvi >= 0.55:
        green.append(f"Dalaning asosiy qismida vegetatsiya ko'rsatkichi (NDVI: {latest_ndvi:.2f}) yuqori va me'yorda rivojlanmoqda.")
    else:
        green.append(f"Dala maydonida o'sish dinamikasi kuzatilmoqda (NDVI: {latest_ndvi:.2f}).")

    if latest_ndmi >= 0.25:
        green.append("O'simlik to'qimalarida suv ta'minoti va barg turgori yetarli darajada saqlanmoqda.")

    if latest_ndre >= 0.35:
        green.append("Xlorofill va azot balansi ijobiy dinamikada, fotosintez faolligi optimal.")

    advice = {"red": red[:3], "yellow": yellow[:3], "green": green[:3]}
    content = f"{crop_name} maydoni bo'yicha Sentinel-2 5 bosqichli biofizik va fazoviy anomaliyalar tahlili asosida agronomik xulosa shakllantirildi."
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
                    {name: render_heatmap(index_values[name], valid, layer_name=name) for name in INDEX_NAMES}
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
                stats = calculate_stats(index_values[name])
                index_data[name] = (relative.as_posix(), stats)
            self.repository.complete_acquisition(
                acquisition_id, index_data, processed_at=created_at
            )
            logger.info(
                "Acquisition processed successfully acquisition_id=%s layers=%d",
                acquisition_id,
                layer_count,
            )

        except Exception as exc:
            self.repository.mark_processing_failure(acquisition_id, str(exc))
            logger.exception("Acquisition processing failed acquisition_id=%s", acquisition_id)
            raise

    async def _fetch_rasters(
        self, field: dict[str, Any], items: list[CatalogItem]
    ) -> list[RasterData | Exception]:
        """Katalog elementlari rasterlarini cheklangan parallelikda yuklash."""
        semaphore = asyncio.Semaphore(RASTER_FETCH_CONCURRENCY)

        async def fetch(item: CatalogItem) -> RasterData | Exception:
            async with semaphore:
                try:
                    return await self.sentinel.raster(field["geometry"], item.acquired_at)
                except Exception as exc:  # noqa: BLE001
                    return exc

        return list(await asyncio.gather(*(fetch(item) for item in items)))

    def _record_stats(self, record: dict[str, Any]) -> IndexStats:
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
        """60 kunlik kuzatuvlar bo'yicha spektral metrikalar taqsimoti."""
        history: dict[str, list[dict[str, Any]]] = {name: [] for name in INDEX_NAMES}
        records = self.repository.index_value_records(field_id, limit=30)
        for record in records:
            cloud = record.get("cloud_coverage")
            stats = self._record_stats(record)
            history[str(record["index_name"])].append(
                {
                    "acquired_at": record["acquired_at"],
                    "product_id": record["product_id"],
                    "cloud_coverage": _round2(cloud),
                    "minimum": _round2(stats.minimum),
                    "mean": _round2(stats.mean),
                    "median": _round2(stats.median),
                    "maximum": _round2(stats.maximum),
                }
            )
        logger.info(
            "60-day AI statistics calculated field_id=%s metrics=%d", field_id, len(history)
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
        newest_raster: RasterData | None = None
        newest_item_time: str = ""

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
            if not isinstance(raster, Exception) and (not newest_item_time or item.acquired_at > newest_item_time):
                newest_raster = raster
                newest_item_time = item.acquired_at

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
            crop = str(field.get("crop_name") or "Ekin")
            history = self._metric_history(field_id)

            # 5-Bosqichli Biofizik Anomaliya tahlili
            anomaly_report: AnomalyAnalysisReport | None = None
            if newest_raster is not None:
                try:
                    anomaly_report = detect_and_cluster_anomalies(
                        newest_raster.bands,
                        valid_pixel_mask(newest_raster),
                        historical_metrics=history,
                        crop_name=crop,
                    )
                except Exception as exc:
                    logger.warning("Anomaly detection failed: %s", exc)

            if self.ai is None:
                recommendation_error = "OPENAI_API_KEY sozlanmagan; avvalgi tavsiya saqlandi"
                if recommendation is None:
                    content, advice = generate_expert_agronomy_advice(
                        crop, history, anomaly_report=anomaly_report
                    )
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
                        field,
                        newest,
                        history,
                        anomaly_report=anomaly_report.to_dict() if anomaly_report else None,
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
                        content, advice = generate_expert_agronomy_advice(
                            crop, history, anomaly_report=anomaly_report
                        )
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
