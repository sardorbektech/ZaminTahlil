import httpx
import pytest
from openai import APIConnectionError

from app.ai import AIClient, AIResult


class FallbackAI(AIClient):
    def __init__(self) -> None:
        self.primary_model = "gpt-5.4-nano"
        self.fallback_model = "gpt-5.4-mini"
        self.calls: list[str] = []

    async def _generate(self, model, input_data, instructions=None):
        self.calls.append(model)
        if model == self.primary_model:
            raise APIConnectionError(request=httpx.Request("POST", "https://api.openai.com"))
        return AIResult("fallback", model)


@pytest.mark.asyncio
async def test_primary_retry_then_fallback(monkeypatch) -> None:
    async def no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr("app.ai.asyncio.sleep", no_sleep)
    client = FallbackAI()
    result = await client.generate_with_fallback(
        "input", instructions="test instructions"
    )
    assert client.calls == ["gpt-5.4-nano", "gpt-5.4-nano", "gpt-5.4-mini"]
    assert result.model_name == "gpt-5.4-mini"
