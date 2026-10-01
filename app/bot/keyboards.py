"""Telegram Bot klaviaturalari va interaktiv tugmalari."""

from __future__ import annotations

from typing import Any
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)


def get_main_reply_keyboard(webapp_url: str | None = None) -> ReplyKeyboardMarkup:
    """Asosiy menyu tugmalari."""
    keyboard = [
        [KeyboardButton(text="🌾 Dalalarim"), KeyboardButton(text="🛰️ Tahlil")],
        [KeyboardButton(text="📊 Indekslar"), KeyboardButton(text="🌱 Hosil")],
        [KeyboardButton(text="🔍 Muammolar"), KeyboardButton(text="📋 Tavsiya")],
        [KeyboardButton(text="🌤️ Ob-havo"), KeyboardButton(text="🤖 AI Agronom")],
        [KeyboardButton(text="ℹ️ Yordam")],
    ]
    if webapp_url:
        from aiogram.types import WebAppInfo
        keyboard.insert(0, [KeyboardButton(text="🗺️ Xaritani ochish", web_app=WebAppInfo(url=webapp_url))])

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        is_persistent=True,
    )


def get_fields_inline_keyboard(fields: list[dict[str, Any]], active_field_id: int | None = None) -> InlineKeyboardMarkup:
    """Dalalarni tanlash uchun inline klaviatura."""
    buttons: list[list[InlineKeyboardButton]] = []
    for f in fields:
        f_id = int(f["id"])
        is_active = f_id == active_field_id
        prefix = "✅ " if is_active else "🌾 "
        title = f"{prefix}{f.get('crop_name', 'Dala')} (#{f_id}, {f.get('area_hectares', 0)} ga)"
        buttons.append([InlineKeyboardButton(text=title, callback_data=f"select_field:{f_id}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_indexes_inline_keyboard(field_id: int) -> InlineKeyboardMarkup:
    """Spektral indekslar xaritasini tanlash tugmalari."""
    buttons = [
        [
            InlineKeyboardButton(text="🌿 NDVI (Vegetatsiya)", callback_data=f"view_index:{field_id}:NDVI"),
            InlineKeyboardButton(text="💧 NDMI (Namlik)", callback_data=f"view_index:{field_id}:NDMI"),
        ],
        [
            InlineKeyboardButton(text="🍃 NDRE (Xlorofill/Azot)", callback_data=f"view_index:{field_id}:NDRE"),
            InlineKeyboardButton(text="🌾 EVI (Biomassa)", callback_data=f"view_index:{field_id}:EVI"),
        ],
        [
            InlineKeyboardButton(text="🏜️ BSI (Sho'rlanish)", callback_data=f"view_index:{field_id}:BSI"),
            InlineKeyboardButton(text="🛰️ RGB (Haqiqiy rang)", callback_data=f"view_index:{field_id}:RGB"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)
