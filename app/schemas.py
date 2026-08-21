from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.constants import MAX_CHAT_MESSAGE_LENGTH, MAX_CHAT_MESSAGES
from app.geometry import GeometryError, validate_polygon_geojson


class FieldCreate(BaseModel):
    geometry: dict[str, Any]
    crop_name: str = Field(min_length=1, max_length=120)
    planted_on: date
    growth_stage: str = Field(min_length=1, max_length=120)

    @field_validator("geometry")
    @classmethod
    def polygon_is_valid(cls, value: dict[str, Any]) -> dict[str, Any]:
        try:
            validate_polygon_geojson(value)
        except GeometryError as exc:
            raise ValueError(str(exc)) from exc
        return value

    @field_validator("crop_name", "growth_stage")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Maydon bo'sh bo'lmasligi kerak")
        return stripped


class FieldOut(BaseModel):
    id: int
    public_id: str | None = None
    geometry: dict[str, Any]
    area_hectares: float
    crop_name: str
    planted_on: date
    growth_stage: str
    created_at: str
    updated_at: str



class AcquisitionOut(BaseModel):
    id: int
    field_id: int
    acquired_at: str
    product_id: str
    revision_key: str
    cloud_coverage: float | None
    processed_at: str | None
    valid_pixel_count: int | None
    fully_cloudy: bool
    processing_error: str | None = None


class AdviceGroups(BaseModel):
    red: list[str] = Field(default_factory=list, max_length=3)
    yellow: list[str] = Field(default_factory=list, max_length=3)
    green: list[str] = Field(default_factory=list, max_length=3)


class RecommendationOut(BaseModel):
    field_id: int
    acquisition_id: int
    content: str
    advice: AdviceGroups
    model_name: str
    created_at: str


class FieldDetail(FieldOut):
    latest_acquisition: AcquisitionOut | None = None
    recommendation: RecommendationOut | None = None


class AnalyzeRequest(BaseModel):
    mode: Literal["latest", "latest_cloud_free"] = "latest"


class AnalyzeResponse(BaseModel):
    selected_acquisition: AcquisitionOut
    new_acquisitions_processed: int
    recommendation: RecommendationOut | None
    recommendation_error: str | None = None


class HistoricalMetricsRequest(BaseModel):
    from_date: date

    @field_validator("from_date")
    @classmethod
    def date_cannot_be_in_the_future(cls, value: date) -> date:
        if value > date.today():
            raise ValueError("Boshlanish sanasi bugundan keyin bo'lishi mumkin emas")
        return value


class ArtifactOut(BaseModel):
    id: int
    acquisition_id: int
    layer_name: str
    bbox: list[float]
    width: int
    height: int
    render_version: str
    created_at: str
    image_url: str
    mean_value: float | None = None
    min_value: float | None = None
    median_value: float | None = None
    max_value: float | None = None
    layer_valid_pixel_count: int | None = None
    hotspot_coordinates: list[float] | None = None


class AnnualPoint(BaseModel):
    acquisition_id: int
    acquired_at: str
    cloud_coverage: float | None
    fully_cloudy: bool
    values: dict[str, float | None]


class AnnualSeries(BaseModel):
    year: int
    indexes: list[str]
    points: list[AnnualPoint]


class HistoricalSeries(BaseModel):
    from_date: date
    to_date: date
    indexes: list[str]
    points: list[AnnualPoint]


class HistoricalMetricsResponse(BaseModel):
    acquisitions_found: int
    new_acquisitions_processed: int
    series: HistoricalSeries


class ArtifactsResponse(BaseModel):
    field_id: int
    acquisition: AcquisitionOut
    artifacts: list[ArtifactOut]
    hotspot_coordinates: list[float] | None = None


# --- RAG Schemas ---
class RAGIngestRequest(BaseModel):
    pdf_path: str = Field(min_length=1)
    document_name: str | None = None


class RAGDocumentOut(BaseModel):
    id: int
    name: str
    file_path: str
    file_hash: str
    total_pages: int
    chunk_count: int
    created_at: str


class RAGSourceOut(BaseModel):
    document_name: str
    page_number: int
    score: float
    text: str


class RAGBookOut(BaseModel):
    id: int | None = None
    name: str
    file_path: str
    size_mb: float
    total_pages: int | None = None
    chunk_count: int = 0
    embedding_model: str = "nomic-ai/nomic-embed-text-v1.5"
    is_active: bool = True
    indexed: bool = False


class RAGIndexRequest(BaseModel):
    file_name: str


class RAGToggleRequest(BaseModel):
    is_active: bool


# --- Chat Schemas ---
class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=MAX_CHAT_MESSAGE_LENGTH)

    @field_validator("content")
    @classmethod
    def strip_content(cls, value: str) -> str:
        return value.strip()


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=MAX_CHAT_MESSAGES)
    language: Literal["uz-latn", "uz-cyrl", "ru", "en"] | None = None
    selected_book_ids: list[int] | None = None
    rag_mode: Literal["advanced", "all_in_one", "graph", "naive", "direct_llm", "auto"] = "advanced"


class ChatResponse(BaseModel):
    answer: str
    model_name: str
    rag_sources: list[RAGSourceOut] = Field(default_factory=list)
    active_books: list[str] = Field(default_factory=list)
    rag_strategy: str = "advanced"
    rag_source_title: str = "🔬 Advanced RAG"
    summary: str | None = None


class ChatHistoryMessageOut(BaseModel):
    id: int
    field_id: int
    role: Literal["user", "assistant"]
    content: str
    rag_sources: list[dict[str, Any]] | None = None
    rag_strategy: str | None = None
    rag_source_title: str | None = None
    created_at: str


class ChatSummaryOut(BaseModel):
    field_id: int
    summary_text: str
    message_count: int
    last_message_id: int
    updated_at: str


# --- Yield Prediction Schemas ---
class YieldPredictRequest(BaseModel):
    model_name: str = "CatBoost"
    crop: str | None = None
    planting_date: date | None = None
    harvest_date: date | None = None


class FeatureImportanceOut(BaseModel):
    feature: str
    importance: float
    description: str


class PhenologyPointOut(BaseModel):
    month: int
    ndvi: float
    evi: float
    ndre: float
    ndmi: float
    s1_vh: float
    s1_vv_vh: float
    temp_mean: float
    rain_sum: float
    soil_moisture: float


class YieldPredictResponse(BaseModel):
    crop: str
    crop_display_name: str
    model_used: str
    predicted_yield_t_ha: float
    yield_min_expected: float
    yield_max_expected: float
    total_expected_yield_tons: float
    total_yield_min_tons: float
    total_yield_max_tons: float
    field_area_ha: float
    top_features: list[FeatureImportanceOut]
    phenology_timeline: list[PhenologyPointOut]
    features_count: int
    execution_time_sec: float


# --- Database Purge Schemas ---
class PurgeDatabaseRequest(BaseModel):
    confirmation: str