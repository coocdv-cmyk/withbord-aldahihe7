"""Stage 5 contract: a measured, role-bound SFX library with no silent degradation."""
from __future__ import annotations

import json
import math
import wave
from pathlib import Path

import numpy as np
import pytest

from engine.audio import sfx as sfx_mod
from engine.audio.sfx import (
    EVENT_PEAK_CEILING,
    LIBRARY_TARGET_RMS_DBFS,
    SFX_DIR,
    SFX_TYPES,
    build_track,
    library_status,
    load_calibration,
)


def _events(path: Path, events: list[dict], scenes: list[dict] | None = None) -> Path:
    data = {"fps": 24, "scenes": scenes or [], "events": events}
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _read_wav(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as w:
        raw = w.readframes(w.getnframes())
        return np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0


# --------------------------------------------------------------------------
# the library itself
# --------------------------------------------------------------------------
def test_library_is_complete_and_every_recording_has_a_role():
    status = library_status()
    assert status["complete"] is True
    assert status["missing"] == []
    assert status["types"] == len(SFX_TYPES)
    # every type points at a recording that exists and has a declared role
    for name, spec in SFX_TYPES.items():
        assert spec.get("role")
        assert spec.get("description")
        assert (SFX_DIR / str(spec["source"])).exists()


def test_every_recording_is_licensed():
    data = json.loads((SFX_DIR / "LICENSES.json").read_text(encoding="utf-8"))
    licensed = {entry["file"] for entry in data["files"]}
    used = {str(spec["source"]) for spec in SFX_TYPES.values()}
    assert used <= licensed
    for entry in data["files"]:
        assert entry.get("license")
        assert entry.get("role")
        assert (SFX_DIR / entry["file"]).exists()


def test_calibration_table_is_committed_and_current():
    table = load_calibration()
    assert table, "calibration.json must be committed"
    for name, spec in SFX_TYPES.items():
        source = str(spec["source"])
        entry = table["recordings"].get(source)
        assert entry, f"no calibration for {source}"
        assert entry["sha256"]
        assert isinstance(entry["calibration_gain_db"], (int, float))
    # the tool can reproduce the table (the check mode compares the hashes)
    assert sfx_mod.library_status()["calibration"] is True


def test_recordings_are_distinct_enough_to_keep_both():
    """Two files of the same sound would duplicate a role."""
    table = load_calibration()
    records = list(table["recordings"].values())
    for i, a in enumerate(records):
        for b in records[i + 1 :]:
            same_character = abs(a["centroid_hz"] - b["centroid_hz"]) < 120
            same_level = abs(a["lufs_raw"] - b["lufs_raw"]) < 3
            assert not (same_character and same_level), (
                f"{a['role']} and {b['role']} are not distinct enough"
            )


# --------------------------------------------------------------------------
# binding and levels
# --------------------------------------------------------------------------
def test_semantic_binding_maps_element_types_to_sound_types():
    assert sfx_mod._bind_stroke("text") == "scratch"
    assert sfx_mod._bind_stroke("svg") == "scratch"
    assert sfx_mod._bind_stroke("underline") == "scratch_soft"
    assert sfx_mod._bind_stroke("flourish") == "scratch_fast"
    assert sfx_mod._bind_place("paper_card") == "page"
    assert sfx_mod._bind_place("texture") == "page_soft"
    # unknown element types fall back to the main writing texture
    assert sfx_mod._bind_stroke(None) == "scratch"


def test_events_are_bound_by_the_element_type(tmp_path: Path):
    events = [
        {"t": 0.10, "kind": "down", "el_type": "text"},
        {"t": 0.40, "kind": "up", "el_type": "text"},
        {"t": 0.60, "kind": "down", "el_type": "underline"},
        {"t": 0.80, "kind": "up", "el_type": "underline"},
        {"t": 1.00, "kind": "down", "el_type": "flourish"},
        {"t": 1.10, "kind": "up", "el_type": "flourish"},
        {"t": 1.30, "kind": "tap"},
        {"t": 1.50, "kind": "place", "el_type": "paper_card"},
    ]
    src = _events(tmp_path / "e.sfx.json", events)
    out = tmp_path / "o.wav"
    info = build_track(src, out, duration=2.0)
    counts = info["counts_by_type"]
    assert counts.get("scratch") == 1
    assert counts.get("scratch_soft") == 1
    assert counts.get("scratch_fast") == 1
    assert counts.get("tick") == 1
    assert counts.get("page") == 1
    assert info["synthetic_fallback"] is False


def test_every_event_is_measured_to_the_library_target(tmp_path: Path):
    """Each placed excerpt sits at the library level, not at a hand-picked one."""
    events = [
        {"t": 0.10, "kind": "down", "el_type": "text"},
        {"t": 0.40, "kind": "up", "el_type": "text"},
    ]
    src = _events(tmp_path / "e.sfx.json", events)
    out = tmp_path / "o.wav"
    info = build_track(src, out, duration=1.5)
    track = _read_wav(out)
    assert info["library_target_rms_dbfs"] == LIBRARY_TARGET_RMS_DBFS
    # the level of the event itself (not of the whole track, whose average
    # depends on how much of the timeline carries sound)
    loud = np.abs(track) > 0.01
    assert loud.any()
    window = track[loud]
    rms = 20 * math.log10(float(np.sqrt(np.mean(window.astype(np.float64) ** 2))) or 1e-12)
    assert rms == pytest.approx(LIBRARY_TARGET_RMS_DBFS, abs=1.5)
    assert float(np.max(np.abs(track))) <= EVENT_PEAK_CEILING + 1e-6


def test_the_report_is_measured_not_guessed(tmp_path: Path):
    events = [{"t": 0.1, "kind": "tap"}]
    src = _events(tmp_path / "e.sfx.json", events)
    out = tmp_path / "o.wav"
    info = build_track(src, out, duration=1.0)
    for key in (
        "track_rms_dbfs",
        "track_peak_dbfs",
        "library_target_rms_dbfs",
        "counts_by_type",
        "missing_recordings",
        "synthetic_fallback",
        "real_recordings",
        "preset",
        "sources",
    ):
        assert key in info
    assert info["sources"] and all(s["file"] for s in info["sources"])


def test_a_missing_recording_is_reported_not_hidden(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(sfx_mod, "SFX_DIR", tmp_path / "empty")
    events = [{"t": 0.1, "kind": "tap"}]
    src = _events(tmp_path / "e.sfx.json", events)
    out = tmp_path / "o.wav"
    info = build_track(src, out, duration=1.0)
    assert info["synthetic_fallback"] is True
    assert info["real_recordings"] is False
    assert info["missing_recordings"]


def test_library_status_reports_missing_recordings(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(sfx_mod, "SFX_DIR", tmp_path / "empty")
    status = library_status()
    assert status["complete"] is False
    assert status["missing"]


# --------------------------------------------------------------------------
# sync: the sound must land where the picture happens
# --------------------------------------------------------------------------
def test_sfx_events_stay_inside_the_output_bounds(tmp_path: Path):
    events = [
        {"t": 0.0, "kind": "down", "el_type": "text"},
        {"t": 0.5, "kind": "up", "el_type": "text"},
        {"t": 9.9, "kind": "tap"},
        {"t": 12.0, "kind": "tap"},   # outside the 10 s output
        {"t": -0.5, "kind": "tap"},   # before the output
    ]
    src = _events(tmp_path / "e.sfx.json", events)
    out = tmp_path / "o.wav"
    info = build_track(src, out, duration=10.0)
    assert info["dropped_events"] == 2
    track = _read_wav(out)
    # the last audible energy must be inside the output window
    loud = np.where(np.abs(track) > 0.001)[0]
    if loud.size:
        assert loud[-1] <= 10.0 * sfx_mod.SR + 1
