"""Bounded Qwen 4B assistant for research tasks.

The assistant is never the final authority.  It proposes structured values that
must be validated against supplied sources, and unavailability is reported as a
distinct state rather than being disguised as completion.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

import requests

from ..core.config import load_config
from ..core.log import get_logger

log = get_logger("research_assistant")

_DEFAULT_MODEL_DIR = (
    Path(os.environ["RASM_MODEL_DIR"])
    if os.environ.get("RASM_MODEL_DIR")
    else Path(__file__).resolve().parents[3] / "studio" / "models"
)
DEFAULT_MODEL_PATH = _DEFAULT_MODEL_DIR / "Qwen3-4B-Instruct-2507-Q4_K_M.gguf"


@dataclass
class AssistantConfig:
    base_url: str = "http://127.0.0.1:11435/v1"
    model: str = "qwen3:4b"
    api_key: str = ""
    model_path: Path | None = None
    context_size: int = 8192
    max_tokens: int = 900
    timeout: int = 120
    retries: int = 2
    temperature: float = 0.1

    def to_safe_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["api_key"] = "***" if self.api_key else ""
        d["model_path"] = str(self.model_path) if self.model_path else ""
        return d


def load_assistant_config(cfg=None) -> AssistantConfig:
    cfg = cfg or load_config()
    research_cfg = cfg.get("research", "assistant", default={}) or {}
    base_url = os.environ.get("RASM_RESEARCH_LLM_BASE_URL") or research_cfg.get("base_url") or cfg.get("llm", "local_base_url", default="http://127.0.0.1:11435/v1")
    model = os.environ.get("RASM_RESEARCH_LLM_MODEL") or research_cfg.get("model") or cfg.get("llm", "local_model", default="qwen3:4b")
    api_key = (
        os.environ.get("RASM_RESEARCH_LLM_API_KEY")
        or research_cfg.get("api_key")
        or cfg.get("llm", "api_key", default="")
    )
    if not api_key:
        # the local llama-server writes its key to a file; without it every
        # request answers 401 and the model looks broken
        try:
            from ..providers.llm import local_api_key

            api_key = local_api_key()
        except Exception:
            api_key = ""
    model_path_raw = os.environ.get("RASM_RESEARCH_LLM_MODEL_PATH") or research_cfg.get("model_path") or cfg.get("llm", "model_path", default="")
    if not model_path_raw and DEFAULT_MODEL_PATH.exists():
        model_path_raw = str(DEFAULT_MODEL_PATH)
    model_path = Path(model_path_raw) if model_path_raw else None
    return AssistantConfig(
        base_url=base_url,
        model=model,
        api_key=api_key,
        model_path=model_path,
        context_size=int(research_cfg.get("context_size", cfg.get("llm", "context_size", default=8192))),
        max_tokens=int(research_cfg.get("max_tokens", 900)),
        timeout=int(research_cfg.get("timeout", 120)),
        retries=int(research_cfg.get("retries", 2)),
        temperature=float(research_cfg.get("temperature", 0.1)),
    )


class ResearchAssistant:
    def __init__(self, config: AssistantConfig | None = None):
        self.config = config or load_assistant_config()
        self._status: dict[str, Any] | None = None

    def model_identity(self) -> dict[str, Any]:
        path = self.config.model_path
        if not path or not path.exists():
            return {"path": str(path) if path else "", "exists": False, "size_bytes": 0, "sha256": ""}
        stat = path.stat()
        # Hashing a 2.5 GB model is expensive; keep it optional and bounded.
        sha = ""
        try:
            if stat.st_size < 25_000_000:
                h = hashlib.sha256()
                with path.open("rb") as f:
                    for chunk in iter(lambda: f.read(1024 * 1024), b""):
                        h.update(chunk)
                sha = h.hexdigest()
        except Exception:
            sha = ""
        return {"path": str(path), "exists": True, "size_bytes": stat.st_size, "sha256": sha}

    def probe(self) -> dict[str, Any]:
        started = time.monotonic()
        status = {
            "available": False,
            "backend": "offline",
            "http_status": None,
            "error_type": "",
            "error": "",
            "model": self.config.model,
            "base_url": self.config.base_url,
            "model_identity": self.model_identity(),
            "latency_ms": 0,
            "models": [],
        }
        url = self.config.base_url.rstrip("/") + "/models"
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        try:
            response = requests.get(url, headers=headers, timeout=min(self.config.timeout, 10))
            status["http_status"] = response.status_code
            status["latency_ms"] = int((time.monotonic() - started) * 1000)
            if response.status_code == 401:
                status["error_type"] = "auth_401"
                status["error"] = "authentication rejected (HTTP 401)"
                return status
            if response.status_code == 403:
                status["error_type"] = "auth_403"
                status["error"] = "access forbidden (HTTP 403)"
                return status
            if response.status_code >= 500:
                status["error_type"] = "server_error"
                status["error"] = f"server error (HTTP {response.status_code})"
                return status
            response.raise_for_status()
            data = response.json()
            models = [m.get("id") or m.get("name") for m in data.get("data", []) or data.get("models", []) or []]
            status["models"] = [m for m in models if m]
            status["available"] = True
            status["backend"] = "local"
            return status
        except requests.ConnectionError as exc:
            status["error_type"] = "connection_error"
            status["error"] = f"connection failed: {exc}"
        except requests.Timeout as exc:
            status["error_type"] = "timeout"
            status["error"] = f"timeout: {exc}"
        except Exception as exc:
            status["error_type"] = "unknown"
            status["error"] = str(exc)[:300]
        status["latency_ms"] = int((time.monotonic() - started) * 1000)
        return status

    def chat_json(self, system: str, user: str, *, schema: dict[str, Any] | None = None,
                 max_tokens: int | None = None, temperature: float | None = None) -> dict[str, Any]:
        status = self.probe()
        if not status["available"]:
            raise RuntimeError(f"assistant unavailable: {status['error_type']}: {status['error']}")
        url = self.config.base_url.rstrip("/") + "/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user + "\n/no_think"},
            ],
            "temperature": self.config.temperature if temperature is None else temperature,
            "max_tokens": min(self.config.max_tokens, max_tokens or self.config.max_tokens),
        }
        if schema:
            payload["response_format"] = {"type": "json_object"}
        last_error = None
        for attempt in range(self.config.retries + 1):
            try:
                response = requests.post(url, headers=headers, json=payload, timeout=self.config.timeout)
                if response.status_code >= 400:
                    payload.pop("response_format", None)
                    response = requests.post(url, headers=headers, json=payload, timeout=self.config.timeout)
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
                data = _extract_json(content)
                if data is None:
                    raise ValueError("no JSON in assistant response")
                if schema:
                    _validate_schema(data, schema)
                return data
            except Exception as exc:
                last_error = exc
                log.warning("assistant attempt %d failed: %s", attempt + 1, exc)
        raise RuntimeError(f"assistant JSON failed: {last_error}")

    # Bounded task helpers.  Each validates a minimal contract; callers still
    # have to verify every value against supplied sources.
    def propose_units(self, text: str) -> dict[str, Any]:
        schema = {"type": "object", "required": ["units"], "properties": {"units": {"type": "array"}}}
        return self.chat_json(
            "You group script cues into meaningful explanatory units. Return JSON only. "
            "Do not invent facts. Each unit needs id, cue_indices, text, purpose.",
            text[:6000],
            schema=schema,
            max_tokens=900,
        )

    def draft_queries(self, requirement: dict[str, Any]) -> dict[str, Any]:
        schema = {"type": "object", "required": ["queries"], "properties": {"queries": {"type": "array"}}}
        return self.chat_json(
            "Draft concise source-discovery queries for one research requirement. "
            "Return JSON only: {queries:[{query, provider, rationale}]}. "
            "provider must be one of: wikipedia, wikidata, wikimedia_commons, local_icon_library. "
            "Do not propose providers that are not in that list. Do not assert that results exist.",
            json.dumps(requirement, ensure_ascii=False)[:4000],
            schema=schema,
            max_tokens=700,
        )

    def suggest_alternatives(self, name: str, context: str) -> dict[str, Any]:
        schema = {"type": "object", "required": ["alternatives"], "properties": {"alternatives": {"type": "array"}}}
        return self.chat_json(
            "Suggest verified-search alternative names for an entity. These are "
            "unverified suggestions until supported by a source.",
            f"name={name}\ncontext={context}",
            schema=schema,
            max_tokens=500,
        )

    def extract_fields(self, source_text: str, fields: list[str]) -> dict[str, Any]:
        schema = {"type": "object", "required": ["fields"], "properties": {"fields": {"type": "object"}}}
        return self.chat_json(
            "Extract only fields that are explicitly supported by the supplied source text. "
            "Return {fields:{...}, unsupported:[...]}.",
            f"fields={fields}\nsource={source_text[:5000]}",
            schema=schema,
            max_tokens=700,
        )

    def compare_candidates(self, candidates: list[dict[str, Any]]) -> dict[str, Any]:
        schema = {"type": "object", "required": ["comparison"], "properties": {"comparison": {"type": "array"}}}
        return self.chat_json(
            "Compare candidates using only cited evidence. Do not decide final approval.",
            json.dumps(candidates, ensure_ascii=False)[:6000],
            schema=schema,
            max_tokens=900,
        )

    def next_action(self, state: dict[str, Any]) -> dict[str, Any]:
        schema = {"type": "object", "required": ["action"], "properties": {"action": {"type": "string"}}}
        return self.chat_json(
            "Choose the next research action from: search, read, extract, verify, stop. "
            "Return {action, reason, budget_impact}.",
            json.dumps(state, ensure_ascii=False)[:5000],
            schema=schema,
            max_tokens=400,
        )

    def summarize_unresolved(self, state: dict[str, Any]) -> dict[str, Any]:
        schema = {"type": "object", "required": ["summary"], "properties": {"summary": {"type": "string"}}}
        return self.chat_json(
            "Summarise unresolved requirements honestly. Do not claim completion.",
            json.dumps(state, ensure_ascii=False)[:6000],
            schema=schema,
            max_tokens=700,
        )


def _extract_json(text: str) -> dict[str, Any] | None:
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
                        return json.loads(text[start:i + 1])
                    except Exception:
                        break
        start = text.find("{", start + 1)
    return None


def _validate_schema(data: dict[str, Any], schema: dict[str, Any]) -> None:
    if schema.get("type") == "object" and not isinstance(data, dict):
        raise ValueError("expected object")
    for key in schema.get("required", []):
        if key not in data:
            raise ValueError(f"missing required field: {key}")
    props = schema.get("properties", {})
    for key, spec in props.items():
        if key in data and "type" in spec:
            expected = spec["type"]
            value = data[key]
            if expected == "object" and not isinstance(value, dict):
                raise ValueError(f"{key} must be object")
            if expected == "array" and not isinstance(value, list):
                raise ValueError(f"{key} must be array")
            if expected == "string" and not isinstance(value, str):
                raise ValueError(f"{key} must be string")
