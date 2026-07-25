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


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=MAX_CHAT_MESSAGE_LENGTH)

    @field_validator("content")
    @classmethod
    def strip_content(cls, value: str) -> str:
        return value.strip()


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=MAX_CHAT_MESSAGES)
    # Frontend tanlagan til — ixtiyoriy. Faqat matn tilini avtomatik aniqlab
    # bo'lmagandagina javob tili sifatida ishlatiladi.
    language: Literal["uz-latn", "uz-cyrl", "ru", "en"] | None = None


class ChatResponse(BaseModel):
    answer: str
    model_name: str