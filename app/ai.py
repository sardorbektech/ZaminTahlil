import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, cast

from openai import (
    APIConnectionError,
    APITimeoutError,
    AsyncOpenAI,
    InternalServerError,
    RateLimitError,
)

from app.constants import AI_CHAT_SYSTEM_PROMPT, AI_RECOMMENDATION_SYSTEM_PROMPT
from app.language import LANGUAGE_NAMES, SUPPORTED_LANGUAGES, detect_language

logger = logging.getLogger(__name__)


class AIError(RuntimeError):
    pass


@dataclass(frozen=True)
class AIResult:
    content: str
    model_name: str
    advice: dict[str, list[str]] | None = None


ADVICE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        name: {"type": "array", "items": {"type": "string"}, "maxItems": 3}
        for name in ("red", "yellow", "green")
    },
    "required": ["red", "yellow", "green"],
    "additionalProperties": False,
}


class AIClient:
    def __init__(
        self,
        api_key: str,
        *,
        primary_model: str,
        fallback_model: str,
        timeout: float,
    ) -> None:
        self.client = AsyncOpenAI(api_key=api_key, timeout=timeout, max_retries=0)
        self.primary_model = primary_model
        self.fallback_model = fallback_model

    async def _generate(
        self, model: str, input_data: Any, instructions: str
    ) -> AIResult:
        response = await self.client.responses.create(
            model=model,
            instructions=instructions,
            input=input_data,
        )
        content = response.output_text.strip()
        if not content:
            raise AIError("AI bo'sh javob qaytardi")
        logger.info("AI response generated model=%s", model)
        return AIResult(content, model)

    async def _generate_advice(
        self, model: str, input_data: Any, instructions: str
    ) -> AIResult:
        response = await self.client.responses.create(
            model=model,
            instructions=instructions,
            input=input_data,
            text=cast(
                Any,
                {
                    "format": {
                        "type": "json_schema",
                        "name": "field_advice",
                        "strict": True,
                        "schema": ADVICE_SCHEMA,
                    }
                },
            ),
        )
        try:
            raw = json.loads(response.output_text)
            if not isinstance(raw, dict) or any(
                not isinstance(raw.get(name), list)
                or any(not isinstance(item, str) for item in raw[name])
                for name in ("red", "yellow", "green")
            ):
                raise TypeError
            advice = {
                name: [str(item).strip() for item in raw[name] if str(item).strip()][:3]
                for name in ("red", "yellow", "green")
            }
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise AIError("AI tavsiya formatini noto'g'ri qaytardi") from exc
        labels = {
            "red": "Qilinishi shart",
            "yellow": "Chorasi ko'rilishi kerak",
            "green": "Yaxshi jarayonlar",
        }
        content = "\n\n".join(
            f"{labels[name]}:\n" + "\n".join(f"- {item}" for item in advice[name])
            for name in ("red", "yellow", "green")
            if advice[name]
        )
        if not content:
            content = "Berilgan ma'lumotlar asosida alohida choralar aniqlanmadi."
        logger.info(
            "AI structured advice generated model=%s red=%d yellow=%d green=%d",
            model,
            len(advice["red"]),
            len(advice["yellow"]),
            len(advice["green"]),
        )
        return AIResult(content, model, advice)

    async def generate_with_fallback(
        self, input_data: Any, *, instructions: str, structured_advice: bool = False
    ) -> AIResult:
        retryable = (
            APIConnectionError,
            APITimeoutError,
            RateLimitError,
            InternalServerError,
        )
        generate = self._generate_advice if structured_advice else self._generate
        for attempt in range(2):
            try:
                return await generate(self.primary_model, input_data, instructions)
            except retryable:
                if attempt == 0:
                    await asyncio.sleep(0.5)
        try:
            return await generate(self.fallback_model, input_data, instructions)
        except Exception as exc:
            raise AIError("AI tavsiyasi hozir yaratilmadi") from exc

    async def recommendation(
        self,
        field: dict[str, Any],
        acquisition: dict[str, Any],
        history: dict[str, list[dict[str, Any]]],
    ) -> AIResult:
        allowed_context = {
            "field": {
                "crop_name": field["crop_name"],
                "area_hectares": field["area_hectares"],
                "planted_on": field["planted_on"],
                "growth_stage": field["growth_stage"],
            },
            "acquisition": {
                "acquired_at": acquisition["acquired_at"],
                "product_id": acquisition["product_id"],
                "cloud_coverage": acquisition["cloud_coverage"],
                "fully_cloudy": bool(acquisition["fully_cloudy"]),
                "statistics_are_null": bool(acquisition["fully_cloudy"]),
            },
            "last_five_observations_for_important_metrics": history,
        }
        return await self.generate_with_fallback(
            json.dumps(allowed_context, ensure_ascii=False),
            instructions=AI_RECOMMENDATION_SYSTEM_PROMPT,
            structured_advice=True,
        )

    async def chat(
        self,
        field: dict[str, Any],
        recommendation: dict[str, Any],
        messages: list[dict[str, str]],
        *,
        language: str | None = None,
    ) -> AIResult:
        context = {
            "current_recommendation": recommendation["content"],
            "field": {
                "crop_name": field["crop_name"],
                "area_hectares": field["area_hectares"],
                "planted_on": field["planted_on"],
                "growth_stage": field["growth_stage"],
            },
        }
        inputs: list[dict[str, Any]] = [
            {
                "role": "user",
                "content": "Loyiha konteksti (fakt sifatida ishlating): "
                + json.dumps(context, ensure_ascii=False),
            }
        ]
        inputs.extend(messages)

        # Javob tili ustuvorligi: matnda aniq so'ralgan til (LLM ko'rsatmasi orqali)
        # > avtomatik aniqlangan matn tili > frontend tili.
        last_user_text = next(
            (m["content"] for m in reversed(messages) if m.get("role") == "user"),
            "",
        )
        detected = detect_language(last_user_text) if last_user_text else None
        target = detected or language
        if target in SUPPORTED_LANGUAGES:
            instructions = AI_CHAT_SYSTEM_PROMPT + (
                f"\n\nJavob tili: {LANGUAGE_NAMES[target]} tili. "
                "Javobni aynan shu tilda yozing. "
                "Faqat foydalanuvchi oxirgi xabarida javob tilini aniq boshqacha "
                "so'ragan bo'lsa, so'ralgan tilda javob bering."
            )
        else:
            instructions = AI_CHAT_SYSTEM_PROMPT

        return await self.generate_with_fallback(
            inputs,
            instructions=instructions,
            structured_advice=False,
        )
