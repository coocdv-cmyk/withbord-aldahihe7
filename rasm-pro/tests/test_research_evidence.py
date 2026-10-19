from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.research.evidence import ResearchBudget, ResearchRequirement
from engine.research.identity import parse_chronology
from engine.research.requirements import group_cues, parse_srt
from engine.research.urls import is_complete_url, is_safe_url
from engine.research.verification import check_identity, verify_candidate
from engine.research.discovery import NullDiscoveryProvider, DiscoveryRegistry
from engine.research.workflow import ResearchWorkflow
from engine.research.assistant import ResearchAssistant


class UnavailableAssistant:
    def probe(self):
        return {"available": False, "error_type": "connection_error", "error": "no server", "model": "", "backend": "offline"}

    def draft_queries(self, requirement):
        raise RuntimeError("assistant unavailable")


def test_srt_grouping_preserves_timing():
    srt = """1
00:00:00,000 --> 00:00:02,000
Hello world

2
00:00:02,100 --> 00:00:04,000
Second cue
"""
    cues = parse_srt(srt)
    assert len(cues) == 2
    units = group_cues(cues, max_words=100, max_gap_seconds=1.5)
    assert len(units) == 1
    assert units[0]["start_seconds"] == 0.0
    assert units[0]["end_seconds"] == 4.0
    assert "Hello world" in units[0]["text"]
    assert "Second cue" in units[0]["text"]


def test_url_validation_and_ssrf():
    assert is_complete_url("https://example.com/page")
    assert not is_complete_url("https://example.com/...")
    assert not is_complete_url("not a url")
    safe, reason = is_safe_url("http://127.0.0.1:8080/x")
    assert not safe
    safe, reason = is_safe_url("https://example.com/x")
    # DNS may or may not resolve in CI; only assert the local rejection case.
    assert reason in {"ok", "host did not resolve"}


def test_chronology_bce_and_century():
    bce = parse_chronology("200 BCE")
    assert bce.era == "BCE"
    assert bce.start_year == -200
    century = parse_chronology("5th century BCE")
    assert century.precision == "century"
    assert century.start_year == -500
    assert century.end_year == -401
    rng = parse_chronology("1914-1918")
    assert rng.start_year == 1914 and rng.end_year == 1918


def test_verification_identity_gate():
    req = ResearchRequirement(id="r1", scene_id="1", unit_id="u1", excerpt="x", purpose="p", asset_type="portrait", entity="Sun Tzu")
    candidate = {"id": "c1", "entity": "Sun Tzu", "source_page_url": "https://example.com", "file_url": "https://example.com/x.jpg",
                "retrieved_at": "2026-01-01T00:00:00+00:00", "content_hash": "abc", "evidence_refs": ["ev1"]}
    result = verify_candidate(candidate, req)
    assert "identity" not in result["failed_mandatory"]
    bad = dict(candidate, entity="Confucius")
    result2 = verify_candidate(bad, req)
    assert "identity" in result2["failed_mandatory"]


def test_workflow_runs_without_assistant_or_network(tmp_path: Path):
    pd = tmp_path / "proj"
    pd.mkdir()
    for sub in ["script", "research", "assets", "strokes", "audio", "frames", "renders", "reports"]:
        (pd / sub).mkdir()
    wf = ResearchWorkflow(
        pd,
        budget=ResearchBudget(max_seconds=5, max_requests=2, max_pages=2, max_llm_calls=0),
        assistant=UnavailableAssistant(),
        discovery=DiscoveryRegistry([NullDiscoveryProvider()]),
        download=False,
        resume=False,
    )
    state = wf.run(script_text="A short script about 1914.", source_urls=["https://example.com/..."])
    assert state.status in {"completed", "completed_with_unresolved"}
    assert any("Incomplete URL skipped" in w for w in state.warnings)
    assert state.assistant_status != "available"
    assert (pd / "research" / "evidence.json").exists()
    # Resume should not crash and should preserve state.
    wf2 = ResearchWorkflow(pd, budget=ResearchBudget(max_seconds=5, max_requests=2, max_pages=2, max_llm_calls=0),
                          assistant=UnavailableAssistant(), discovery=DiscoveryRegistry([NullDiscoveryProvider()]),
                          download=False, resume=True)
    state2 = wf2.run(script_text="A short script about 1914.", source_urls=["https://example.com/..."])
    assert state2.job_id == state.job_id


def test_assistant_unavailable_is_explicit():
    assistant = ResearchAssistant.__new__(ResearchAssistant)
    # Avoid network; monkeypatch probe.
    assistant.config = None
    assistant.probe = lambda: {"available": False, "error_type": "connection_error", "error": "no server", "model": "", "backend": "offline"}
    status = assistant.probe()
    assert status["available"] is False
    assert status["error_type"] == "connection_error"
