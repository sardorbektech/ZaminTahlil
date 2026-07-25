"""Production security utilities: HTTP security headers va loglardagi
maxfiy ma'lumotlarni maskalash uchun yordamchi modullar."""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from typing import Any

from app.config import Settings

# Har bir javobga qo'shiladigan statik xavfsizlik sarlavhalari.
# Strict-Transport-Security esa faqat HTTPS so'rovlarga qo'shiladi (pastda).
_STATIC_SECURITY_HEADERS: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}

_HSTS_HEADER = "Strict-Transport-Security"
_HSTS_VALUE = "max-age=31536000; includeSubDomains"

# Loglardagi maxfiy ma'lumotlarni aniqlash uchun regex andozalari.
_BEARER_PATTERN = re.compile(r"Bearer\s+\S+", re.IGNORECASE)
_OPENAI_KEY_PATTERN = re.compile(r"sk-[A-Za-z0-9_-]{6,}")
_KV_PATTERN = re.compile(
    r"(?i)(client_secret|client_id|api_key|access_token|refresh_token|token|password|secret"
    r"|authorization|cookie|set-cookie)([\"'\s:=]+)([^\s,\"'&]{4,})"
)


def _is_https(scope: dict[str, Any]) -> bool:
    """So'rov HTTPS orqali kelganini aniqlaydi."""
    if scope.get("scheme") == "https":
        return True
    for header_name, header_value in scope.get("headers") or ():
        if header_name == b"x-forwarded-proto" and header_value.split(b",", 1)[0].strip() == b"https":
            return True
    return False


class SecurityHeadersMiddleware:
    """Har bir javobga xavfsizlik sarlavhalarini qo'shuvchi sof ASGI middleware.

    Strict-Transport-Security faqat HTTPS so'rovlarga qo'shiladi."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        is_https = _is_https(scope)

        async def send_wrapper(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                headers: list[list[bytes]] = list(message.get("headers") or [])
                for name, value in _STATIC_SECURITY_HEADERS.items():
                    headers.append([name.encode("latin-1"), value.encode("latin-1")])
                if is_https:
                    headers.append([_HSTS_HEADER.encode("latin-1"), _HSTS_VALUE.encode("latin-1")])
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_wrapper)


class SensitiveDataFilter(logging.Filter):
    """Log yozuvlaridagi maxfiy ma'lumotlarni (API kalitlari, tokenlar,
    parollar va boshqalar) maskalaydi. Prodyusshen loglarida hech qachon
    maxfiy qiymatlar ko'rinishi mumkin emas."""

    def __init__(self, extra_secrets: Iterable[str] | None = None) -> None:
        super().__init__()
        self._extra_secrets: list[str] = [
            secret for secret in (extra_secrets or ()) if secret and len(secret) >= 6
        ]

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        masked = _mask_message(message, self._extra_secrets)
        if masked != message:
            record.msg = masked
            record.args = ()
        return True


def _mask_message(message: str, extra_secrets: list[str]) -> str:
    """Berilgan xabardagi barcha maxfiy qiymatlarni maskalaydi."""
    result = _BEARER_PATTERN.sub("Bearer ***", message)
    result = _OPENAI_KEY_PATTERN.sub("sk-***", result)
    result = _KV_PATTERN.sub(r"\1\2***", result)
    for secret in extra_secrets:
        if secret and secret in result:
            result = result.replace(secret, "***")
    return result


def configure_logging(settings: Settings) -> None:
    """Root logger'dagi barcha handlerlarga SensitiveDataFilter bog'laydi.

    Faqat prod rejimida chaqiriladi (basicConfig dan keyin)."""
    secrets = [
        settings.openai_api_key,
        settings.sentinel_hub_client_id,
        settings.sentinel_hub_client_secret,
    ]
    sensitive_filter = SensitiveDataFilter(secrets)
    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        if not any(
            isinstance(f, SensitiveDataFilter) for f in handler.filters
        ):
            handler.addFilter(sensitive_filter)
