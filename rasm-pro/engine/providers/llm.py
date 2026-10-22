"""مزوّدو الذكاء الاصطناعي — واجهة موحّدة قابلة للتبديل (محلي/أونلاين/بلا)."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import requests

from ..core.config import load_config
from ..core.log import get_logger

log = get_logger("llm")


class LLMError(RuntimeError):
    pass


def _extract_json(text: str) -> dict | None:
    """يستخرج أول كائن JSON متوازن من نص (حتى لو فيه كلام أو أسوار كود)."""
    text = text.strip()
    if text.startswith("```"):
        text = "\n".join(line for line in text.splitlines() if not line.strip().startswith("```")).strip()
    start = text.find("{")
    while start != -1:
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except Exception:
                        break
        start = text.find("{", start + 1)
    return None


def local_api_key() -> str:
    """The key the local llama-server expects (``--api-key-file``).

    The server writes it to ``studio/data/model-key.txt``; without it every
    request answers **401** and the local model looks broken.  The environment
    variable wins, then the key file.
    """
    key = os.environ.get("RASM_LLM_API_KEY") or os.environ.get("RASM_RESEARCH_LLM_API_KEY") or ""
    if key:
        return key.strip()
    here = Path(__file__).resolve()
    for candidate in (
        here.parents[3] / "studio" / "data" / "model-key.txt",
        here.parents[2] / "data" / "model-key.txt",
        here.parents[2] / "studio" / "data" / "model-key.txt",
    ):
        try:
            if candidate.exists():
                return candidate.read_text(encoding="utf-8").strip()
        except Exception:
            continue
    return ""


class LLM:
    """عميل LLM موحّد: local (llama.cpp/ollama) أو openai-compatible أو offline."""

    def __init__(self, cfg=None, *, timeout: int = 180):
        self.cfg = cfg or load_config()
        self.timeout = timeout
        self._backend: str | None = None

    # ---------- اكتشاف الخلفية ----------
    def backend(self) -> str:
        if self._backend:
            return self._backend
        want = self.cfg.llm_backend
        if want == "offline":
            self._backend = "offline"
        elif want == "local":
            self._backend = "local" if self._local_alive() else "offline"
        elif want == "openai":
            self._backend = "openai" if self.cfg.openai_key else "offline"
        else:  # auto — local first, never a silent paid/cloud fallback
            if self._local_alive():
                self._backend = "local"
            else:
                self._backend = "offline"
        log.info("LLM backend = %s", self._backend)
        return self._backend

    def _local_alive(self) -> bool:
        base = self.cfg.get("llm", "local_base_url", default="http://127.0.0.1:11435/v1")
        try:
            r = requests.get(f"{base.rstrip('/')}/models", timeout=2, headers=self._local_headers())
            # a 401 means the server is there but wants the key: that is alive,
            # not "no server".  Treating 401 as dead is what made the local
            # model look unusable.
            return r.status_code < 500
        except Exception:
            return False

    def _local_key(self) -> str:
        """The key the local server expects (llama-server --api-key-file)."""
        return local_api_key()

    def _local_headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        key = self._local_key()
        if key:
            headers["Authorization"] = f"Bearer {key}"
        return headers

    @property
    def available(self) -> bool:
        return self.backend() != "offline"

    # ---------- الاستدعاء ----------
    def chat(self, messages: list[dict], *, temperature: float = 0.2, max_tokens: int | None = None,
             json_mode: bool = False) -> str:
        backend = self.backend()
        if backend == "offline":
            raise LLMError("لا يوجد مزوّد LLM متاح (شغّل llama-server محليًا أو اضبط مفتاح API)")

        if backend == "local":
            base = self.cfg.get("llm", "local_base_url", default="http://127.0.0.1:11435/v1")
            model = self.cfg.get("llm", "local_model", default="qwen3")
            headers = self._local_headers()
        else:
            base = self.cfg.openai_base
            model = self.cfg.model
            headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self.cfg.openai_key}"}

        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        # Qwen3: تعطيل التفكير لردود JSON سريعة (يدعم /no_think في القالب)
        if backend == "local" and "qwen3" in str(model).lower():
            msgs = [dict(m) for m in messages]
            if msgs:
                msgs[-1]["content"] = msgs[-1]["content"] + "\n/no_think"
            payload["messages"] = msgs
        if max_tokens:
            payload["max_tokens"] = max_tokens
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        r = requests.post(f"{base.rstrip('/')}/chat/completions", headers=headers, json=payload, timeout=self.timeout)
        if r.status_code >= 400:
            # بعض المزودين لا يدعمون response_format
            if json_mode:
                payload.pop("response_format", None)
                r = requests.post(f"{base.rstrip('/')}/chat/completions", headers=headers, json=payload, timeout=self.timeout)
        if r.status_code >= 400:
            raise LLMError(f"LLM HTTP {r.status_code}: {r.text[:400]}")
        data = r.json()
        try:
            return data["choices"][0]["message"]["content"]
        except Exception as e:  # pragma: no cover
            raise LLMError(f"رد غير متوقع من المزوّد: {str(data)[:300]}") from e

    def ask_json(self, system: str, user: str, *, temperature: float = 0.15, retries: int = 2) -> dict:
        """يطلب JSON ويستخرجه بمرونة مع إعادة المحاولة."""
        last_err: Exception | None = None
        for attempt in range(retries + 1):
            try:
                text = self.chat(
                    [{"role": "system", "content": system}, {"role": "user", "content": user}],
                    temperature=temperature if attempt == 0 else 0.0,
                    json_mode=True,
                )
                data = _extract_json(text)
                if data is not None:
                    return data
                last_err = LLMError("لا JSON في الرد")
            except Exception as e:
                last_err = e
            log.warning("محاولة LLM %d فشلت: %s", attempt + 1, last_err)
        raise LLMError(f"فشل الحصول على JSON: {last_err}")
