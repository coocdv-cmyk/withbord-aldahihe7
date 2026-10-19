"""Tiny rules-based art director for asset choice.

This is intentionally not an LLM. It maps scene language and purpose to the
locked set of paper/collage assets, with alternatives for the studio to try.
"""
from __future__ import annotations

import re


def _norm(text: str) -> str:
    text = (text or "").lower()
    text = re.sub(r"[\u064B-\u065F\u0670\u06D6-\u06ED]", "", text)
    text = text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    text = text.replace("ى", "ي").replace("ة", "ه")
    text = re.sub(r"\s+", " ", text).strip()
    return text


MOODS: list[tuple[tuple[str, ...], str, list[str]]] = [
    (("حرب", "معرك", "تاريخ", "ارشيف", "قديم", "ماضي", "قرن", "وثيق", "خريط", "1914", "1918", "1945", "war", "history", "archive", "vintage", "map"),
     "history", ["aged_paper", "newsprint", "parchment", "map_fragment", "vintage_poster"]),
    (("علم", "تقني", "هندس", "بيان", "رقم", "احصا", "شبك", "مخطط", "blueprint", "science", "data", "engineer", "chart"),
     "technical", ["grid_paper", "blueprint", "aged_paper", "poster"]),
    (("اقتباس", "رسال", "كلم", "مذكرات", "يومي", "شهاد", "خطاب", "quote", "letter", "diary", "note"),
     "letter", ["parchment", "postcard", "torn_paper", "lined_paper"]),
    (("نبات", "زهر", "طبيع", "botanical", "plant", "flower", "nature"),
     "botanical", ["botanical_print", "collage_element", "parchment"]),
    (("كولاج", "ملصق", "بوستر", "فن", "تصميم", "collage", "poster", "art", "design"),
     "collage", ["vintage_poster", "poster", "paper_scrap", "collage_element"]),
    (("خبر", "صحيف", "جريد", "عنوان", "news", "newspaper", "headline"),
     "news", ["newsprint", "aged_paper", "torn_paper"]),
]

PURPOSE_DEFAULTS = {
    "background": ["aged_paper", "parchment", "newsprint", "grid_paper", "kraft_paper"],
    "card": ["postcard", "torn_paper", "parchment", "poster"],
    "scrap": ["paper_scrap", "sticker", "label_tag", "collage_element", "botanical_print"],
    "overlay": ["tape_strip", "ink_stain", "halftone", "fold_lines", "vignette_overlay"],
}


def suggest(scene_text: str, purpose: str = "background") -> dict:
    text = _norm(scene_text)
    mood = "neutral"
    mood_kinds: list[str] = []
    for keys, name, kinds in MOODS:
        if any(k in text for k in keys):
            mood = name
            mood_kinds = list(kinds)
            break
    defaults = PURPOSE_DEFAULTS.get(purpose, PURPOSE_DEFAULTS["background"])
    kinds: list[str] = []
    for k in mood_kinds + defaults:
        if k not in kinds:
            kinds.append(k)
    return {
        "mood": mood,
        "purpose": purpose,
        "kind": kinds[0] if kinds else "aged_paper",
        "alternatives": kinds[1:5],
        "reason": f"{mood} mood + {purpose} purpose",
    }
