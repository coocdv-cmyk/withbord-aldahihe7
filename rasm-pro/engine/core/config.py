"""الإعدادات: config.json + متغيرات البيئة.""" 
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from .paths import CONFIG_FILE
from .util import read_json

DEFAULTS: dict[str, Any] = {
    "llm": {
        # backend: "local" | "openai" | "offline" | "auto"
        # "auto" is local-first and never falls back to a paid cloud endpoint.
        "backend": "local",
        "local_base_url": "http://127.0.0.1:11435/v1",
        "local_model": "qwen3",
        "openai_base_url": "https://api.openai.com/v1",
        "openai_model": "gpt-4o-mini",
    },
    "tts": {
        "backend": "none",          # none | edge | azure | elevenlabs | local
        "voice": "",
        "rate": "+0%",
    },
    "research": {
        "user_agent": "rasm-pro/0.1 (personal video engine; contact: local)",
        "langs": ["ar", "en"],
        "max_assets_per_need": 3,
        "min_image_width": 640,
        "allow_sharealike": True,   # CC BY-SA: يُسمح مع نسبة
        "download_timeout": 45,
    },
    "render": {
        "fps": 24,
        "width": 2560,
        "height": 1440,
        "draw_speed_px_s": 520,     # سرعة القلم الافتراضية بوحدات اللوح
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


@dataclass
class Config:
    data: dict = field(default_factory=dict)

    def get(self, *path: str, default: Any = None) -> Any:
        node: Any = self.data
        for p in path:
            if not isinstance(node, dict) or p not in node:
                return default
            node = node[p]
        return node

    # --- LLM ---
    @property
    def llm_backend(self) -> str:
        env = os.environ.get("RASM_LLM_BACKEND")
        return env or self.get("llm", "backend", default="local")

    @property
    def openai_key(self) -> str:
        return (
            os.environ.get("RASM_LLM_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
            or os.environ.get("GEMINI_API_KEY")
            or self.get("llm", "api_key", default="")
        )

    @property
    def openai_base(self) -> str:
        key = os.environ.get("GEMINI_API_KEY") or ""
        if key and not (os.environ.get("RASM_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")):
            # Gemini عبر واجهة OpenAI المتوافقة
            return "https://generativelanguage.googleapis.com/v1beta/openai"
        return self.get("llm", "openai_base_url", default=DEFAULTS["llm"]["openai_base_url"])

    @property
    def model(self) -> str:
        if os.environ.get("RASM_LLM_MODEL"):
            return os.environ["RASM_LLM_MODEL"]
        if os.environ.get("GEMINI_API_KEY") and not (os.environ.get("RASM_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")):
            return "gemini-flash-latest"
        return self.get("llm", "openai_model", default=DEFAULTS["llm"]["openai_model"])


_cached: Config | None = None


def load_config(reload: bool = False) -> Config:
    global _cached
    if _cached is not None and not reload:
        return _cached
    data = _deep_merge(DEFAULTS, read_json(CONFIG_FILE, default={}) or {})
    _cached = Config(data)
    return _cached
