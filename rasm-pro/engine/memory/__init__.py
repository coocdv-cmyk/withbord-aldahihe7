"""ذاكرة التعلّم (تصحيحات متراكمة + قواعد مدمجة)."""
from .lexicon import (
    DEFAULT_ALIASES,
    MEM_FILE,
    Lexicon,
    add_correction,
    is_generic_collective,
    looks_like_work,
)

__all__ = [
    "DEFAULT_ALIASES",
    "MEM_FILE",
    "Lexicon",
    "add_correction",
    "is_generic_collective",
    "looks_like_work",
]
