from __future__ import annotations

import json
from pathlib import Path

from engine.core.config import DEFAULTS, Config
from engine.core.util import write_json
from engine.providers.llm import LLM


def test_local_first_defaults():
    assert DEFAULTS["llm"]["backend"] == "local"
    assert Config({"llm": {}}).llm_backend == "local"


def test_auto_never_silently_uses_openai(monkeypatch):
    cfg = Config(
        {
            "llm": {
                "backend": "auto",
                "openai_base_url": "https://api.openai.com/v1",
                "api_key": "should-not-be-used",
            }
        }
    )
    llm = LLM(cfg)
    monkeypatch.setattr(llm, "_local_alive", lambda: False)
    assert llm.backend() == "offline"


def test_write_json_is_atomic_and_roundtrips(tmp_path):
    p = tmp_path / "x.json"
    write_json(p, {"a": 1})
    write_json(p, {"a": 2})
    assert json.loads(p.read_text(encoding="utf-8")) == {"a": 2}
    assert not list(Path(tmp_path).glob(".x.json.*.tmp"))
