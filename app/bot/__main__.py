"""ZaminTahlil Telegram Bot mustaqil (standalone) ishga tushirish moduli.

Ishga tushirish:
    python -m app.bot
yoki
    .venv\\Scripts\\python.exe -m app.bot
"""

from __future__ import annotations

import asyncio
import logging
import sys

from fastapi import FastAPI

from app.ai import create_ai_service
from app.config import get_settings
from app.db import Database
from app.logging import configure_logging
from app.rendering import ArtifactWriter
from app.repository import Repository
from app.sentinel import create_sentinel_client
from app.bot.service import start_telegram_bot


async def run_bot_cli() -> None:
    settings = get_settings()
    configure_logging(settings)
    logger = logging.getLogger("app.bot")

    if not settings.telegram_bot_token or not settings.telegram_bot_token.strip():
        logger.error(
            "❌ XATOLIK: .env faylida TELEGRAM_BOT_TOKEN topilmadi yoki bo'sh!\n"
            "Telegram botni ishga tushirish uchun .env faylingizga quyidagicha token qo'shing:\n"
            "TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz\n"
        )
        sys.exit(1)

    logger.info("🌿 ZaminTahlil Telegram Bot mustaqil rejimda tayyorlanmoqda...")

    # Ma'lumotlar bazasi va xizmatlarni tayyorlash
    database = Database(settings.database_path)
    database.initialize()
    repository = Repository(database)
    artifact_writer = ArtifactWriter(settings.artifact_dir)
    sentinel = create_sentinel_client(settings)
    ai = create_ai_service(settings)

    # Mock/Minimal FastAPI app container
    app = FastAPI(title="ZaminTahlil Bot Runner")
    app.state.settings = settings
    app.state.database = database
    app.state.repository = repository
    app.state.artifact_writer = artifact_writer
    app.state.sentinel = sentinel
    app.state.ai = ai

    logger.info("🚀 Telegram Bot ishga tushirilmoqda. To'xtatish uchun Ctrl+C bosing.")
    try:
        await start_telegram_bot(app)
    except KeyboardInterrupt:
        logger.info("Bot qo'lda to'xtatildi.")
    finally:
        if sentinel is not None:
            await sentinel.aclose()


def main() -> None:
    try:
        asyncio.run(run_bot_cli())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
