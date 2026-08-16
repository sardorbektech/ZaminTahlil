import httpx
import pytest

from app.ai import AIClient, AIResult
from app.language import detect_language


def test_detect_language_uz_cyrl() -> None:
    assert detect_language("Ўзбекистонда екип қўйилди") == "uz-cyrl"


def test_detect_language_ru() -> None:
    assert detect_language("Объясни индекс NDVI") == "ru"


def test_detect_language_uz_latn() -> None:
    assert detect_language("NDVI pasayishi nimani anglatadi?") == "uz-latn"


def test_detect_language_en() -> None:
    assert detect_language("Explain NDVI in English please") == "en"


def test_detect_language_undetectable() -> None:
    assert detect_language("") is None
    assert detect_language("123 456") is None
    assert detect_language("??? !!!") is None


class CapturingAI(AIClient):
    """`chat` ichidagi instruction'ni ushlab qoluvchi test dublyori."""

    def __init__(self) -> None:
        self.primary_model = "gpt-test"
        self.fallback_model = "gpt-fallback"
        self.captured_instructions: str | None = None

    async def _generate(self, model, input_data, instructions=None):
        self.captured_instructions = instructions
        return AIResult("ok", model)


@pytest.fixture
def field() -> dict[str, object]:
    return {
        "crop_name": "Paxta",
        "area_hectares": 95.0,
        "planted_on": "2026-04-01",
        "growth_stage": "Gullash",
    }


@pytest.fixture
def recommendation() -> dict[str, str]:
    return {"content": "test tavsiya"}


@pytest.mark.asyncio
async def test_chat_language_directive_english_text(field, recommendation) -> None:
    client = CapturingAI()
    await client.chat(
        field,
        recommendation,
        [{"role": "user", "content": "Explain NDVI in English"}],
        language="uz-latn",
    )
    assert "ingliz" in client.captured_instructions


@pytest.mark.asyncio
async def test_chat_language_directive_uz_latn_text(field, recommendation) -> None:
    client = CapturingAI()
    await client.chat(
        field,
        recommendation,
        [{"role": "user", "content": "NDVI nima?"}],
        language="ru",
    )
    assert "o'zbek (lotin)" in client.captured_instructions


@pytest.mark.asyncio
async def test_chat_language_directive_russian_text(field, recommendation) -> None:
    client = CapturingAI()
    await client.chat(
        field,
        recommendation,
        [{"role": "user", "content": "Объясни индекс NDVI"}],
        language="en",
    )
    assert "rus" in client.captured_instructions


@pytest.mark.asyncio
async def test_chat_language_directive_fallback_to_frontend(field, recommendation) -> None:
    client = CapturingAI()
    await client.chat(
        field,
        recommendation,
        [{"role": "user", "content": "??? 123"}],
        language="en",
    )
    assert "ingliz" in client.captured_instructions
