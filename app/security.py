"""Production security utilities: HTTP security headers va loglardagi
maxfiy ma'lumotlarni maskalash uchun yordamchi modullar."""

from __future__ import annotations

import collections
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import logging
import os
import re
import threading
import time
from collections.abc import Iterable
from typing import Any

import jwt

from app.config import Settings


def hash_password(password: str) -> str:
    """Parolni PBKDF2-HMAC-SHA256 yordamida tuz va 100,000 iteratsiya bilan xeshlaydi."""
    salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
    return f"{salt.hex()}${key.hex()}"


def verify_password(password: str, hashed: str) -> bool:
    """Parolni xesh bilan xavfsiz (constant-time) solishtiradi."""
    try:
        salt_hex, key_hex = hashed.split("$", 1)
        salt = bytes.fromhex(salt_hex)
        expected_key = bytes.fromhex(key_hex)
        actual_key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
        return hmac.compare_digest(actual_key, expected_key)
    except Exception:
        return False


def create_access_token(
    data: dict[str, Any],
    secret_key: str,
    algorithm: str = "HS256",
    expires_delta: timedelta | None = None,
) -> str:
    """Foydalanuvchi ma'lumotlari asosida JWT access token yaratadi."""
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(days=30)
    to_encode.update({"iat": now, "exp": expire})
    return jwt.encode(to_encode, secret_key, algorithm=algorithm)


def decode_access_token(
    token: str,
    secret_key: str,
    algorithms: list[str] | None = None,
) -> dict[str, Any] | None:
    """JWT access tokenni tekshiradi va dekodlaydi."""
    if algorithms is None:
        algorithms = ["HS256"]
    try:
        return jwt.decode(token, secret_key, algorithms=algorithms)
    except Exception:
        return None

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


class RateLimitMiddleware:
    """Qimmat API operatsiyalari (/analyze, /predict-yield, /chat) uchun
    IP bo'yicha cheklovchi xotiradagi yengil ASGI middleware."""

    def __init__(
        self,
        app: Any,
        max_requests_per_minute: int = 40,
        protected_paths: tuple[str, ...] = ("/analyze", "/predict-yield", "/chat"),
    ) -> None:
        self.app = app
        self.max_requests = max_requests_per_minute
        self.protected_paths = protected_paths
        self._history: dict[str, collections.deque[float]] = {}
        self._lock = threading.Lock()

    def _get_client_ip(self, scope: dict[str, Any]) -> str:
        for header_name, header_value in scope.get("headers") or ():
            if header_name == b"x-forwarded-for":
                try:
                    return header_value.decode("latin-1").split(",")[0].strip()
                except Exception:
                    pass
        client = scope.get("client")
        return client[0] if client else "127.0.0.1"

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if any(path.endswith(p) or f"{p}?" in path for p in self.protected_paths):
            ip = self._get_client_ip(scope)
            now = time.time()
            cutoff = now - 60.0

            with self._lock:
                if len(self._history) > 3000:
                    self._history = {
                        k: q for k, q in self._history.items() if q and q[-1] > cutoff
                    }

                q = self._history.setdefault(ip, collections.deque())
                while q and q[0] <= cutoff:
                    q.popleft()

                if len(q) >= self.max_requests:
                    body = json.dumps(
                        {"detail": "So'rovlar soni me'yordan oshdi. Iltimos, birozdan so'ng qayta urining."}
                    ).encode("utf-8")
                    await send(
                        {
                            "type": "http.response.start",
                            "status": 429,
                            "headers": [
                                [b"content-type", b"application/json"],
                                [b"retry-after", b"30"],
                                [b"content-length", str(len(body)).encode("ascii")],
                            ],
                        }
                    )
                    await send(
                        {
                            "type": "http.response.body",
                            "body": body,
                        }
                    )
                    return

                q.append(now)

        await self.app(scope, receive, send)


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
