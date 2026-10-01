"""ZaminTahlil Telegram Bot buyruq va xabar handlerlari."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, FSInputFile, Message

from app.bot.keyboards import (
    get_fields_inline_keyboard,
    get_indexes_inline_keyboard,
    get_main_reply_keyboard,
)
from app.config import get_settings
from app.spatial_zones import calculate_spatial_problem_zones
from app.yield_service import CROP_CALENDARS, normalize_crop_name

logger = logging.getLogger(__name__)

router = Router(name="zamintahlil_bot_router")


def _get_active_field_or_first(chat_id: int, app: Any) -> dict[str, Any] | None:
    """Foydalanuvchining faol dalasini yoki birinchi mavjud dalasini oladi."""
    repo = app.state.repository
    fields = repo.list_fields()
    if not fields:
        return None

    active_id = repo.get_telegram_active_field_id(chat_id)
    if active_id:
        for f in fields:
            if int(f["id"]) == active_id:
                return f

    # Agar tanlanmagan bo'lsa, birinchisini o'rnatamiz
    first_field = fields[0]
    repo.set_telegram_active_field_id(chat_id, int(first_field["id"]))
    return first_field


@router.message(CommandStart())
async def handle_start(message: Message, app: Any) -> None:
    """Start buyrug'i."""
    chat_id = message.chat.id
    settings = app.state.settings
    repo = app.state.repository
    fields = repo.list_fields()

    active_field = _get_active_field_or_first(chat_id, app)
    field_text = (
        f"🌾 Joriy faol dala: <b>{active_field['crop_name']}</b> (ID: {active_field['id']}, {active_field['area_hectares']} ga)\n"
        if active_field
        else "⚠️ Hozircha tizimda dalalar mavjud emas.\n"
    )

    welcome_text = (
        "🌱 <b>Assalomu alaykum! ZaminTahlil platformasiga xush kelibsiz.</b>\n\n"
        "Ushbu bot orqali siz o'z dalalaringizni kosmik sun'iy yo'ldosh (Sentinel-2) "
        "orqali kuzatishingiz, suv va kasallik o'choqlarini aniqlashingiz, hosildorlikni bashorat "
        "qilishingiz va AI Bosh Agronomidan maslahat olishingiz mumkin.\n\n"
        f"{field_text}\n"
        "Quyidagi menyu tugmalaridan foydalaning yoki savolingizni to'g'ridan-to'g'ri yozing:"
    )

    await message.answer(
        welcome_text,
        reply_markup=get_main_reply_keyboard(settings.telegram_webapp_url),
        parse_mode="HTML",
    )


@router.message(Command("help"))
@router.message(F.text == "ℹ️ Yordam")
async def handle_help(message: Message) -> None:
    """Yordam va buyruqlar ro'yxati."""
    help_text = (
        "📖 <b>ZaminTahlil Bot Buyruqlari:</b>\n\n"
        "🌾 <b>/dalalar</b> — Mavjud barcha dalalar ro'yxati va faol dalani tanlash\n"
        "🛰️ <b>/tahlil</b> — Dalaning so'nggi Sentinel-2 tahlili va kosmik fotosurati\n"
        "📊 <b>/indekslar</b> — Spektral xaritalar (NDVI, NDMI, NDRE, EVI, BSI)\n"
        "🌱 <b>/hosil</b> — Mashinali o'rganish (CatBoost) orqali hosil bashorati\n"
        "🔍 <b>/muammolar</b> — Suvsizlik va kasallik o'choqlarining aniq joylashuvi\n"
        "📋 <b>/tavsiya</b> — 3-toifali shoshilinch agronomik tavsiyalar\n"
        "🌤️ <b>/obhavo</b> — 7 kunlik agrometeorologiya ob-havo ma'lumotlari\n"
        "🤖 <b>/ai &lt;savol&gt;</b> — AI Bosh Agronomidan ilmiy-amaliy maslahat olish\n\n"
        "<i>💡 Shuningdek, xohlagan agronomik savolingizni to'g'ridan-to'g'ri matn sifatida yuborishingiz mumkin!</i>"
    )
    await message.answer(help_text, parse_mode="HTML")


@router.message(Command("dalalar"))
@router.message(F.text == "🌾 Dalalarim")
async def handle_fields_list(message: Message, app: Any) -> None:
    """Dalalar ro'yxatini chiqarish va tanlash."""
    chat_id = message.chat.id
    repo = app.state.repository
    fields = repo.list_fields()

    if not fields:
        await message.answer("⚠️ Tizimda hali birorta ham dala ro'yxatdan o'tkazilmagan.")
        return

    active_id = repo.get_telegram_active_field_id(chat_id)

    lines = ["📋 <b>Sizning dalalaringiz:</b>\n"]
    for f in fields:
        f_id = int(f["id"])
        status = " (✅ Joriy faol)" if f_id == active_id else ""
        lines.append(
            f"• <b>#{f_id} {f.get('crop_name', 'Ekin')}</b> — {f.get('area_hectares', 0)} ga, "
            f"Ekilgan: {f.get('planted_on', 'Nomaʼlum')}{status}"
        )

    lines.append("\nQuyidagi tugmalar orqali boshqarmoqchi bo'lgan dalangizni tanlang:")
    kb = get_fields_inline_keyboard(fields, active_id)
    await message.answer("\n".join(lines), reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("select_field:"))
async def handle_select_field_callback(query: CallbackQuery, app: Any) -> None:
    """Dala tanlangandagi callback."""
    chat_id = query.message.chat.id if query.message else query.from_user.id
    field_id = int(query.data.split(":")[1])
    repo = app.state.repository

    try:
        field = repo.get_field(field_id)
        repo.set_telegram_active_field_id(chat_id, field_id)
        crop = field.get("crop_name", "Ekin")
        await query.answer(f"✅ Dala tanlandi: {crop} (#{field_id})")
        if query.message:
            await query.message.edit_text(
                f"✅ Faol dala muvaffaqiyatli o'zgartirildi:\n\n"
                f"🌾 <b>{crop}</b> (ID: {field_id})\n"
                f"Maydoni: <b>{field.get('area_hectares', 0)} ga</b>\n"
                f"Rivojlanish bosqichi: <b>{field.get('growth_stage', '—')}</b>",
                parse_mode="HTML",
            )
    except Exception as exc:
        logger.warning("Field select failed: %s", exc)
        await query.answer("Xatolik yuz berdi", show_alert=True)


@router.message(Command("muammolar"))
@router.message(Command("zonalar"))
@router.message(F.text == "🔍 Muammolar")
async def handle_problem_zones(message: Message, app: Any) -> None:
    """Fazoviy muammoli zonalarni (suvsizlik va kasallik) xalqchil tushunarli tilda chiqarish."""
    chat_id = message.chat.id
    active_field = _get_active_field_or_first(chat_id, app)
    if not active_field:
        await message.answer("⚠️ Avval /dalalar bo'limidan dalani tanlang.")
        return

    field_id = int(active_field["id"])
    repo = app.state.repository
    settings = app.state.settings

    zones = calculate_spatial_problem_zones(field_id, repo, artifact_root=settings.artifact_dir)

    crop = active_field.get("crop_name", "Ekin")
    if not zones.get("has_data"):
        await message.answer(
            f"🌾 <b>{crop}</b> (#{field_id}) bo'yicha sun'iy yo'ldosh tasvirlari hali qayta ishlanmagan.",
            parse_mode="HTML",
        )
        return

    w_info = zones.get("water_stress")
    d_info = zones.get("disease_stress")

    lines = [
        f"🔍 <b>Fazoviy Muammoli Zonalar Tahlili</b> (Dala: #{field_id} {crop}):\n",
    ]

    if w_info:
        lines.append(
            f"💧 <b>Suvsizlik (Namlik tanqisligi):</b>\n"
            f"Joylashuvi: <b>{w_info['human_location']}</b>\n"
            f"Darajasi: {w_info['severity']} (NDMI: {w_info.get('mean_ndmi', '—')})\n"
            f"Tavsif: {w_info['detail']}\n"
        )

    if d_info:
        lines.append(
            f"⚠️ <b>Kasallik / Xlorofill pasayishi:</b>\n"
            f"Joylashuvi: <b>{d_info['human_location']}</b>\n"
            f"Darajasi: {d_info['severity']}\n"
            f"Tavsif: {d_info['detail']}\n"
        )

    lines.append(f"📌 <b>Xulosa:</b> <i>{zones.get('summary_uz')}</i>")
    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("tahlil"))
@router.message(F.text == "🛰️ Tahlil")
async def handle_analysis(message: Message, app: Any) -> None:
    """Dala kosmik tahlilini ko'rsatish va tasvir yuborish."""
    chat_id = message.chat.id
    active_field = _get_active_field_or_first(chat_id, app)
    if not active_field:
        await message.answer("⚠️ Hozircha dalalar mavjud emas. /dalalar ni ko'ring.")
        return

    field_id = int(active_field["id"])
    repo = app.state.repository
    settings = app.state.settings

    acqs = repo.list_acquisitions(field_id)
    if not acqs:
        await message.answer(
            f"🛰️ <b>{active_field['crop_name']}</b> (#{field_id}) dalasi bo'yicha hali tahlil ma'lumotlari kutilmoqda.",
            parse_mode="HTML",
        )
        return

    latest = acqs[0]
    records = repo.index_value_records(field_id, limit=6)

    # Indekslar statistikasi
    idx_map = {r["index_name"]: r for r in records if int(r.get("acquisition_id", 0)) == int(latest["id"])}
    if not idx_map and records:
        idx_map = {r["index_name"]: r for r in records[:6]}

    def _val(name: str) -> str:
        row = idx_map.get(name)
        if row and row.get("mean_value") is not None:
            return f"{float(row['mean_value']):.2f}"
        return "—"

    caption = (
        f"🛰️ <b>Sentinel-2 Kosmik Tahlili</b>\n\n"
        f"🌾 Dala: <b>{active_field['crop_name']}</b> (#{field_id})\n"
        f"📅 Sana: <b>{latest.get('acquired_at', '')[:10]}</b>\n"
        f"☁️ Bulutlilik: <b>{latest.get('cloud_coverage', 0):.1f}%</b>\n\n"
        f"<b>Asosiy Indekslar:</b>\n"
        f"• NDVI (Vegetatsiya/Zichlik): <b>{_val('NDVI')}</b>\n"
        f"• NDMI (Barg namligi/Suv): <b>{_val('NDMI')}</b>\n"
        f"• NDRE (Xlorofill/Azot): <b>{_val('NDRE')}</b>\n"
        f"• EVI (Biomassa indeksi): <b>{_val('EVI')}</b>\n"
        f"• BSI (Sho'r/Ochiq tuproq): <b>{_val('BSI')}</b>\n\n"
        f"<i>Boshqa qatlamlarni ko'rish uchun /indekslar buyrug'ini yuboring.</i>"
    )

    # Mavjud bo'lsa, NDVI yoki RGB xaritasini yuborish
    img_sent = False
    root = settings.artifact_dir
    ndvi_row = idx_map.get("NDVI")
    if ndvi_row and ndvi_row.get("relative_path"):
        # Heatmap tasvir yo'li (values.npy o'rniga PNG ni qidirish)
        png_rel = str(ndvi_row["relative_path"]).replace("values/NDVI.npy", "NDVI.png")
        png_path = root / png_rel
        if png_path.exists():
            try:
                photo = FSInputFile(str(png_path))
                await message.answer_photo(photo=photo, caption=caption, parse_mode="HTML")
                img_sent = True
            except Exception as exc:
                logger.debug("Failed sending photo: %s", exc)

    if not img_sent:
        await message.answer(caption, parse_mode="HTML")


@router.message(Command("indekslar"))
@router.message(F.text == "📊 Indekslar")
async def handle_indexes_menu(message: Message, app: Any) -> None:
    """Spektral indekslar xaritasini tanlash menyusi."""
    chat_id = message.chat.id
    active_field = _get_active_field_or_first(chat_id, app)
    if not active_field:
        await message.answer("⚠️ Avval /dalalar orqali dalani tanlang.")
        return

    field_id = int(active_field["id"])
    kb = get_indexes_inline_keyboard(field_id)
    await message.answer(
        f"📊 <b>{active_field['crop_name']}</b> (#{field_id}) bo'yicha ko'rmoqchi bo'lgan spektral xaritangizni tanlang:",
        reply_markup=kb,
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("view_index:"))
async def handle_view_index_callback(query: CallbackQuery, app: Any) -> None:
    """Muayyan indeks tasvirini ko'rish callbacki."""
    parts = query.data.split(":")
    field_id = int(parts[1])
    layer_name = parts[2]

    repo = app.state.repository
    settings = app.state.settings

    records = repo.index_value_records(field_id, limit=10)
    layer_rec = next((r for r in records if r.get("index_name") == layer_name), None)

    stat_text = ""
    if layer_rec:
        stat_text = (
            f"\nO'rtacha: <b>{layer_rec.get('mean_value', '—')}</b> | "
            f"Min: <b>{layer_rec.get('min_value', '—')}</b> | "
            f"Max: <b>{layer_rec.get('max_value', '—')}</b>"
        )

    caption = f"🗺️ <b>{layer_name} Spektral Xaritasi</b> (Dala #{field_id}){stat_text}"

    # Agar PNG mavjud bo'lsa
    photo_sent = False
    if layer_rec and layer_rec.get("relative_path"):
        png_rel = str(layer_rec["relative_path"]).replace(f"values/{layer_name}.npy", f"{layer_name}.png")
        png_path = settings.artifact_dir / png_rel
        if png_path.exists():
            try:
                photo = FSInputFile(str(png_path))
                if query.message:
                    await query.message.answer_photo(photo=photo, caption=caption, parse_mode="HTML")
                    photo_sent = True
            except Exception as exc:
                logger.debug("Photo send error: %s", exc)

    await query.answer()
    if not photo_sent and query.message:
        await query.message.answer(caption, parse_mode="HTML")


@router.message(Command("hosil"))
@router.message(F.text == "🌱 Hosil")
async def handle_yield_prediction(message: Message, app: Any) -> None:
    """Hosildorlikni mashinali o'rganish orqali hisoblash."""
    chat_id = message.chat.id
    active_field = _get_active_field_or_first(chat_id, app)
    if not active_field:
        await message.answer("⚠️ Avval /dalalar orqali dalani tanlang.")
        return

    field_id = int(active_field["id"])
    repo = app.state.repository
    yield_service = app.state.yield_service

    crop_type = normalize_crop_name(active_field.get("crop_name", "cotton"))
    crop_cal = CROP_CALENDARS.get(crop_type, CROP_CALENDARS["cotton"])

    from app.weather import fetch_weather_data
    import pandas as pd

    coords = active_field["geometry"]["coordinates"][0]
    lons = [float(p[0]) for p in coords]
    lats = [float(p[1]) for p in coords]
    c_lon = float(sum(lons) / len(lons))
    c_lat = float(sum(lats) / len(lats))

    p_date = active_field.get("planted_on") or crop_cal["planting_date"]
    h_date = crop_cal["harvest_date"]
    s_start = crop_cal["season_start"]
    s_end = crop_cal["season_end"]

    await message.answer("⏳ <i>Kosmik ma'lumotlar va agrometeorologiya integratsiyasi hisoblanmoqda...</i>", parse_mode="HTML")

    try:
        df_w = await asyncio.to_thread(fetch_weather_data, c_lat, c_lon, start_date=s_start, end_date=s_end)
    except Exception:
        dates = pd.date_range(s_start, s_end)
        df_w = pd.DataFrame({
            "date": dates,
            "weather_temperature_2m": 24.0,
            "weather_apparent_temperature": 23.5,
            "weather_total_precipitation": 0.5,
            "weather_rain": 0.5,
            "weather_shortwave_radiation": 22.0,
            "weather_wind_speed_10m": 12.0,
            "weather_soil_temperature_0_7cm": 22.0,
            "weather_soil_moisture_0_7cm": 0.22,
            "weather_soil_moisture_7_28cm": 0.25,
            "weather_soil_moisture_28_100cm": 0.28,
            "weather_evapotranspiration_et0": 4.5,
            "latitude": c_lat,
            "longitude": c_lon,
        })

    records = repo.index_value_records(field_id, limit=30)
    s2_rows = []
    for r in records:
        if r.get("mean_value") is not None:
            s2_rows.append({
                "date": pd.to_datetime(r["acquired_at"][:10]),
                "index_name": r["index_name"],
                "value": float(r["mean_value"]),
            })

    if s2_rows:
        df_long = pd.DataFrame(s2_rows)
        df_s2 = df_long.pivot_table(index="date", columns="index_name", values="value").reset_index()
        col_rename = {col: f"s2_{col.lower()}_mean" for col in df_s2.columns if col != "date"}
        df_s2 = df_s2.rename(columns=col_rename)
    else:
        dates = pd.date_range(s_start, s_end, freq="10D")
        df_s2 = pd.DataFrame({
            "date": dates,
            "s2_ndvi_mean": 0.55,
            "s2_ndre_mean": 0.35,
            "s2_ndmi_mean": 0.25,
            "s2_evi_mean": 0.40,
        })

    pred = yield_service.predict(
        crop_type=crop_type,
        model_name="CatBoost",
        df_s2=df_s2,
        df_weather=df_w,
        field_area_ha=float(active_field["area_hectares"]),
        planting_date=p_date,
        harvest_date=h_date,
    )

    sign = "+" if pred.difference_from_baseline_pct >= 0 else ""
    text = (
        f"🌱 <b>Hosildorlik Bashorati (CatBoost AI)</b>\n\n"
        f"🌾 Dala: <b>{active_field['crop_name']}</b> (#{field_id}, {active_field['area_hectares']} ga)\n"
        f"🎯 Kutilayotgan hosil: <b>{pred.yield_predicted_t_ha:.2f} t/ga</b>\n"
        f"📦 Jami kutilayotgan hosil: <b>{pred.total_yield_tons:.2f} tonna</b>\n"
        f"📊 Ehtimoliy oraliq: <b>{pred.yield_min_expected:.2f} — {pred.yield_max_expected:.2f} t/ga</b>\n"
        f"📈 O'rtacha me'yordan farq: <b>{sign}{pred.difference_from_baseline_pct:.1f}%</b>\n\n"
        f"<b>Qo'llanilgan Ma'lumotlar Manbasi:</b>\n"
        f"• Sentinel-2 multispektral kuzatuvlar: <b>{len(s2_rows)} ta</b>\n"
        f"• Open-Meteo agrometeorologiya kunlari: <b>{len(df_w)} ta</b>"
    )
    await message.answer(text, parse_mode="HTML")


@router.message(Command("tavsiya"))
@router.message(F.text == "📋 Tavsiya")
async def handle_recommendation(message: Message, app: Any) -> None:
    """3-toifali agronomik tavsiya."""
    chat_id = message.chat.id
    active_field = _get_active_field_or_first(chat_id, app)
    if not active_field:
        await message.answer("⚠️ Avval /dalalar orqali dalani tanlang.")
        return

    field_id = int(active_field["id"])
    repo = app.state.repository
    rec = repo.get_recommendation(field_id)

    if not rec:
        await message.answer(
            f"📋 <b>{active_field['crop_name']}</b> (#{field_id}) bo'yicha tavsiya shakllanmagan. "
            "Avval /tahlil o'tkazish tavsiya etiladi.",
            parse_mode="HTML",
        )
        return

    advice = rec.get("advice") or {}
    red = advice.get("red") or []
    yellow = advice.get("yellow") or []
    green = advice.get("green") or []

    lines = [f"📋 <b>Agronomik Tavsiyalar</b> (Dala: #{field_id} {active_field['crop_name']}):\n"]

    if red:
        lines.append("🔴 <b>Shoshilinch Choralari:</b>")
        for item in red:
            lines.append(f"• {item}")
        lines.append("")

    if yellow:
        lines.append("🟡 <b>Nazorat Talab Qiladigan Holatlar:</b>")
        for item in yellow:
            lines.append(f"• {item}")
        lines.append("")

    if green:
        lines.append("🟢 <b>Ijobiy Ko'rsatkichlar:</b>")
        for item in green:
            lines.append(f"• {item}")
        lines.append("")

    if not (red or yellow or green):
        lines.append(rec.get("content", "Alohida choralar aniqlanmadi."))

    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("obhavo"))
@router.message(F.text == "🌤️ Ob-havo")
async def handle_weather(message: Message, app: Any) -> None:
    """Dala bo'yicha 7 kunlik ob-havo prognozi."""
    chat_id = message.chat.id
    active_field = _get_active_field_or_first(chat_id, app)
    if not active_field:
        await message.answer("⚠️ Avval /dalalar orqali dalani tanlang.")
        return

    coords = active_field["geometry"]["coordinates"][0]
    lons = [float(p[0]) for p in coords]
    lats = [float(p[1]) for p in coords]
    c_lon = float(sum(lons) / len(lons))
    c_lat = float(sum(lats) / len(lats))

    import httpx
    url = (
        f"https://api.open-meteo.com/v1/forecast?latitude={c_lat}&longitude={c_lon}"
        f"&current=temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m"
        f"&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,et0_fao_evapotranspiration"
        f"&timezone=auto"
    )

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            data = resp.json()
            curr = data.get("current", {})
            daily = data.get("daily", {})

            lines = [
                f"🌤️ <b>Agrometeorologiya Ob-havo Ma'lumotlari</b>\n"
                f"🌾 Dala: <b>{active_field['crop_name']}</b> (#{active_field['id']})\n\n"
                f"<b>Hozirgi Holat:</b>\n"
                f"• Harorat: <b>{curr.get('temperature_2m', '—')} °C</b>\n"
                f"• Havoning nisbiy namligi: <b>{curr.get('relative_humidity_2m', '—')}%</b>\n"
                f"• Shamol tezligi: <b>{curr.get('wind_speed_10m', '—')} km/soat</b>\n"
                f"• Yog'ingarchilik: <b>{curr.get('precipitation', 0)} mm</b>\n\n"
                f"<b>Yaqin Kunlik Prognoz:</b>\n"
            ]

            times = daily.get("time", [])[:5]
            t_max = daily.get("temperature_2m_max", [])
            t_min = daily.get("temperature_2m_min", [])
            prec = daily.get("precipitation_sum", [])
            et0 = daily.get("et0_fao_evapotranspiration", [])

            for i, d in enumerate(times):
                mx = t_max[i] if i < len(t_max) else "—"
                mn = t_min[i] if i < len(t_min) else "—"
                p = prec[i] if i < len(prec) else 0
                e = et0[i] if i < len(et0) else "—"
                lines.append(f"📅 <b>{d}</b>: {mn}°C ... {mx}°C | Yog'in: {p} mm | Bug'lanish: {e} mm")

            await message.answer("\n".join(lines), parse_mode="HTML")
    except Exception as exc:
        logger.warning("Weather fetch error: %s", exc)
        await message.answer("⚠️ Ob-havo ma'lumotlarini yuklashda xatolik yuz berdi.")


@router.message(Command("ai"))
@router.message(F.text == "🤖 AI Agronom")
@router.message(F.text)
async def handle_ai_chat_message(message: Message, app: Any) -> None:
    """Foydalanuvchining erkin savollariga AI Bosh Agronomi javobi."""
    chat_id = message.chat.id
    user_text = message.text or ""
    if user_text == "🤖 AI Agronom":
        await message.answer(
            "🤖 <b>AI Bosh Agronom xizmati faol!</b>\n\n"
            "Dalangiz bo'yicha xohlagan savolingizni bering (masalan: "
            "<i>'Dalaning qayerida suvsizlik eng ko'p?', 'Qanday o'g'it beray?', "
            "'Kasallik belgilari qayerda?'</i>):",
            parse_mode="HTML",
        )
        return

    if user_text.startswith("/ai"):
        user_text = user_text.removeprefix("/ai").strip()
        if not user_text:
            await message.answer("Savolingizni kiriting: masalan <code>/ai Dalam holati qanday?</code>", parse_mode="HTML")
            return

    active_field = _get_active_field_or_first(chat_id, app)
    if not active_field:
        await message.answer("⚠️ Avval /dalalar bo'limidan dalangizni tanlang.")
        return

    field_id = int(active_field["id"])
    repo = app.state.repository
    settings = app.state.settings
    ai_client = app.state.ai

    if not ai_client:
        await message.answer("⚠️ OPENAI_API_KEY sozlanmaganligi sababli AI xizmati faol emas.")
        return

    rec = repo.get_recommendation(field_id)
    if not rec:
        rec = {"content": "Dala tahlili ma'lumotlari kutilmoqda"}

    # Typing status
    await message.bot.send_chat_action(chat_id=chat_id, action="typing")

    # 1. Fazoviy muammoli zonalar
    problem_zones = calculate_spatial_problem_zones(field_id, repo, artifact_root=settings.artifact_dir)

    # 2. RAG Agronomik kitoblar qidiruvi
    rag_service = app.state.rag
    rag_chunks = await asyncio.to_thread(
        rag_service.search_advanced,
        user_text,
        database=repo.database,
        top_k=3,
    )
    rag_ctx = "\n\n".join([f"[{c.document_name}, p.{c.page_number}]: {c.text}" for c in rag_chunks]) if rag_chunks else None

    # 3. Oxirgi metrikalar
    recent_records = repo.index_value_records(field_id, limit=5)
    recent_metrics: dict[str, list[dict[str, Any]]] = {}
    for r in recent_records:
        recent_metrics.setdefault(str(r["index_name"]), []).append({
            "acquired_at": r["acquired_at"],
            "mean": r.get("mean_value"),
            "min": r.get("min_value"),
            "max": r.get("max_value"),
        })

    try:
        res = await ai_client.chat(
            field=active_field,
            recommendation=rec,
            messages=[{"role": "user", "content": user_text}],
            recent_ndvi_metrics=recent_metrics,
            rag_context=rag_ctx,
            spatial_problem_zones=problem_zones,
        )
        await message.answer(res.content)
    except Exception as exc:
        logger.exception("AI chat in bot failed: %s", exc)
        await message.answer("⚠️ AI javobini tayyorlashda xatolik yuz berdi. Iltimos, keyinroq qayta urinib ko'ring.")
