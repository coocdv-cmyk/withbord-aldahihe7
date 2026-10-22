"""Regression: كتابة سكريبت من فكرة — بالعقد، وباحتياطي حتمي صريح.

* الموديل يعيد JSON ⇒ scenes صحيحة.
* مسودّة غير صالحة (نصّ، أو مشاهد فارغة) ⇒ **لا تُقبل**: ننتقل إلى الهيكل
  الحتمي ونقول ذلك.
* الهيكل الحتمي نفسه صالح (مشاهد بطول قابل للرسم).
"""
from __future__ import annotations

import json

import pytest

from engine.stages.script_writer import (
    ScriptError,
    fallback_scenes,
    script_to_graph,
    validate_scenes,
    write_script,
)


class _FakeLLM:
    """A model double: it returns what the test hands it."""

    available = True

    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def backend(self) -> str:
        return "fake"

    def ask_json(self, system, user, **kwargs):
        self.calls += 1
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


def test_a_model_answer_becomes_scenes():
    llm = _FakeLLM({"scenes": [{"text": "لماذا ننسى ما نتعلمه؟ الجواب في ثلاثة أشياء."}]})
    result = write_script("الذاكرة", scenes=4, llm=llm)
    assert result["mode"] == "llm:fake"
    assert result["scenes"][0]["text"].startswith("لماذا")
    assert llm.calls == 1


def test_a_broken_answer_falls_back_and_says_so():
    llm = _FakeLLM({"scenes": []})
    result = write_script("الذاكرة", scenes=4, llm=llm)
    assert result["mode"] == "fallback"
    assert result["scenes"]
    assert result["reason"]


def test_an_unreachable_model_falls_back_and_says_so():
    from engine.providers.llm import LLMError

    llm = _FakeLLM(LLMError("no server"))
    result = write_script("الذاكرة", scenes=4, llm=llm)
    assert result["mode"] == "fallback"
    assert "no server" in result["reason"]


def test_a_scene_that_is_too_long_is_cut():
    parsed = validate_scenes([{"text": " ".join(["word"] * 60)}])
    assert parsed[0]["words"] <= 33
    assert parsed[0]["text"].endswith("…")


def test_the_deterministic_outline_is_usable():
    scenes = fallback_scenes("فن الحرب", 8)
    assert len(scenes) == 8
    for scene in scenes:
        assert scene["words"] >= 8


def test_the_draft_becomes_a_script_graph():
    result = {"scenes": fallback_scenes("فن الحرب", 5), "mode": "fallback", "language": "ar"}
    graph = script_to_graph(result)
    assert len(graph["scenes"]) == 5
    assert graph["scenes"][0]["id"] == 1
    assert graph["engine"].startswith("script:")
    assert graph["lang"] == "ar"
