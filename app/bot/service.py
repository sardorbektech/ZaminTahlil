"""Telegram Bot xizmati (Polling va Lifespan boshqaruvi)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from aiogram import Bot, Dispatcher
from fastapi import FastAPI

from app.bot.handlers import router

logger = logging.getLogger(__name__)

_bot_instance: Bot | None = None
_dispatcher_instance: Dispatcher | None = None


async def start_telegram_bot(app: FastAPI) -> None:
    """Telegram botni fonda ishga tushiradi."""
    global _bot_instance, _dispatcher_instance

    settings = app.state.settings
    token = settings.telegram_bot_token
    if not token or not token.strip():
        logger.info("TELEGRAM_BOT_TOKEN sozlanmagan, bot ishga tushirilmaydi.")
        return

    logger.info("🤖 Telegram Bot ishga tushirilmoqda...")
    bot = Bot(token=token.strip())
    dp = Dispatcher()

    # app obyektini barcha handlerlarga dependency sifatida uzatish
    dp["app"] = app

    router.parent_router = None
    dp.include_router(router)

    _bot_instance = bot
    _dispatcher_instance = dp

    try:
        bot_info = await bot.get_me()
        logger.info("✅ Telegram Bot muvaffaqiyatli ishga tushdi: @%s (%s)", bot_info.username, bot_info.first_name)
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, handle_signals=False)
    except asyncio.CancelledError:
        logger.info("Telegram Bot polling to'xtatildi (Cancelled).")
    except Exception as exc:
        logger.exception("❌ Telegram Bot ishida xatolik yuz berdi (token yoki internet aloqasini tekshiring): %s", exc)
    finally:
        await bot.session.close()
        logger.info("Telegram Bot sessiyasi yopildi.")


async def stop_telegram_bot() -> None:
    """Telegram bot polling va sessiyasini to'xtatadi."""
    global _bot_instance, _dispatcher_instance
    if _dispatcher_instance is not None:
        try:
            if hasattr(_dispatcher_instance, "_running_lock") and _dispatcher_instance._running_lock.locked():
                await _dispatcher_instance.stop_polling()
        except Exception as exc:
            logger.debug("Dispatcher stop_polling xatolik: %s", exc)
        _dispatcher_instance = None
    if _bot_instance is not None:
        try:
            await _bot_instance.session.close()
        except Exception as exc:
            logger.debug("Bot session close xatolik: %s", exc)
        _bot_instance = None
    logger.info("Telegram Bot to'xtatildi.")
