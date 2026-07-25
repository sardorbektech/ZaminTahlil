"""Foydalanuvchi xabar matnidan javob tilini aniqlash.

Ustuvorlik tartibi:
  1. Foydalanuvchi xabarida javob tilini aniq so'rashi (LLM prompt orqali hal qilinadi).
  2. Xabar matni tilining avtomatik aniqlanishi — shu tilda javob beriladi.
  3. Frontend tanlagan til (mijozdan keladigan `language` maydoni) — faqat avtomatik
     aniqlanmagan taqdirda ishlatiladi.

Hech qanday tashqi bog'liqlikka ega emas — sof Python heuristikasi.
"""

import re
from typing import Final

SUPPORTED_LANGUAGES: Final[tuple[str, ...]] = ("uz-latn", "uz-cyrl", "ru", "en")

LANGUAGE_NAMES: Final[dict[str, str]] = {
    "uz-latn": "o'zbek (lotin)",
    "uz-cyrl": "o'zbek (kirill)",
    "ru": "rus",
    "en": "ingliz",
}

_CYRILLIC_RE = re.compile(r"[а-яёА-ЯЁ]")
_UZ_CYRILLIC_RE = re.compile(r"[ЎўҚқҒғҲҳ]")
_LATIN_RE = re.compile(r"[A-Za-z]")
_OZ_APOSTROPHE_RE = re.compile(r"o'|O'|G'|g'")

_UZ_MARKERS: Final[tuple[str, ...]] = (
    "va", "uchun", "bilan", "nima", "qanday", "nega", "ekin", "dala",
    "suv", "juda", "emas", "bormi", "kerak", "qiling", "tushuntiring",
    "yo'q", "haqida", "indeks", "anglatadi", "pasayishi", "nimani",
)
_EN_MARKERS: Final[tuple[str, ...]] = (
    "the", "is", "are", "what", "how", "why", "explain", "please",
    "in", "on", "field", "crop", "water", "mean", "does", "this",
    "that", "and", "you",
)


def _word_hits(text: str, words: tuple[str, ...]) -> int:
    """Matnda berilgan to'xtatuvchi so'zlar necha marta uchraganini sanaydi."""
    hits = 0
    for word in words:
        hits += len(re.findall(rf"\b{re.escape(word)}\b", text))
    return hits


def detect_language(text: str) -> str | None:
    """Matn tilini aniqlaydi.

    SUPPORTED_LANGUAGES ichidan birini yoki aniqlanmagan taqdirda None qaytaradi.
    Kiril yozuvida o'zbekcha maxsus harflar borligi tekshiriladi, aks holda rus
    deb hisoblanadi. Lotin yozuvida o'zbek va ingliz markerlari hisoblanadi.
    """
    if not text:
        return None

    if _CYRILLIC_RE.search(text):
        if _UZ_CYRILLIC_RE.search(text):
            return "uz-cyrl"
        return "ru"

    if not _LATIN_RE.search(text):
        return None

    lowered = text.lower()
    uz_score = _word_hits(lowered, _UZ_MARKERS)
    uz_score += len(_OZ_APOSTROPHE_RE.findall(text))
    en_score = _word_hits(lowered, _EN_MARKERS)

    if uz_score > en_score and uz_score > 0:
        return "uz-latn"
    if en_score > uz_score and en_score > 0:
        return "en"
    return None
