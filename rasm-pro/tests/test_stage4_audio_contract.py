"""Stage 4 contract: loudness measurement, measured alignment, and the narration gate."""
from __future__ import annotations

import json
import math
import shutil
import wave
from pathlib import Path

import numpy as np
import pytest

from engine.audio.align import (
    LEVEL_MEASURED,
    LEVEL_NONE,
    LEVEL_SEGMENTED,
    detect_speech,
    measured_align,
)
from engine.audio.gate import evaluate_narration_gate
from engine.audio.loudness import (
    LoudnessError,
    measure_loudness,
    measure_samples,
)
from engine.audio.narration import (
    load_narration,
    normalize_narration,
    resolve_narration,
)

RATE = 22050


def _tone(seconds: float, freq: float = 220.0, amp: float = 0.3, rate: int = RATE) -> np.ndarray:
    t = np.arange(int(seconds * rate)) / rate
    return (amp * np.sin(2 * math.pi * freq * t)).reshape(1, -1)


def _write_wav(path: Path, samples: np.ndarray, rate: int = RATE) -> Path:
    data = np.clip(samples[0], -1.0, 1.0)
    pcm = (data * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())
    return path


# --------------------------------------------------------------------------
# loudness
# --------------------------------------------------------------------------
def test_loudness_of_a_1khz_tone_matches_its_rms():
    """BS.1770-4: for a 1 kHz tone the reading equals the mean-square level."""
    x = _tone(10.0, 1000.0, amp=10 ** (-20 / 20), rate=48000)  # -20 dBFS peak => -23 dBFS RMS
    report = measure_samples(x, 48000)
    assert report.lufs_integrated == pytest.approx(-23.0, abs=0.4)
    assert report.rms_dbfs == pytest.approx(-23.01, abs=0.05)
    assert report.true_peak_dbtp == pytest.approx(-20.0, abs=0.1)


def test_loudness_stereo_gets_three_lu_more_than_mono():
    mono = _tone(6.0, 1000.0, amp=10 ** (-20 / 20))
    stereo = np.concatenate([mono, mono], axis=0)
    a = measure_samples(mono, 48000).lufs_integrated
    b = measure_samples(stereo, 48000).lufs_integrated
    assert b - a == pytest.approx(3.0, abs=0.2)


def test_loudness_k_weighting_attenuates_low_frequencies():
    low = measure_samples(_tone(8.0, 60.0, amp=10 ** (-20 / 20)), 48000)
    mid = measure_samples(_tone(8.0, 1000.0, amp=10 ** (-20 / 20)), 48000)
    assert low.lufs_integrated < mid.lufs_integrated - 2.0


def test_loudness_lra_of_two_levels():
    loud = _tone(6.0, 1000.0, amp=10 ** (-20 / 20))
    quiet = _tone(6.0, 1000.0, amp=10 ** (-40 / 20))
    report = measure_samples(np.concatenate([loud, quiet], axis=1), 48000)
    assert report.lra == pytest.approx(20.0, abs=1.0)


def test_loudness_is_deterministic():
    x = _tone(4.0, 1000.0, amp=0.2)
    assert measure_samples(x, 48000).to_dict() == measure_samples(x, 48000).to_dict()


def test_loudness_rejects_an_empty_signal():
    with pytest.raises(LoudnessError):
        measure_samples(np.zeros((1, 0)), 48000)


# --------------------------------------------------------------------------
# measured alignment
# --------------------------------------------------------------------------
def _speech_with_pauses() -> np.ndarray:
    parts = [
        _tone(1.0),
        _tone(0.6, freq=0.0, amp=0.001),
        _tone(1.0),
        _tone(0.6, freq=0.0, amp=0.001),
        _tone(1.0),
    ]
    return np.concatenate(parts, axis=1)


def test_detect_speech_finds_the_pauses_exactly():
    x = _speech_with_pauses()
    segments = detect_speech(x, RATE)
    assert len(segments) == 3
    assert segments[0].start_sample == 0
    assert abs(segments[0].end_sample / RATE - 1.0) < 0.03
    assert abs(segments[1].start_sample / RATE - 1.6) < 0.03
    assert abs(segments[2].end_sample / RATE - 4.2) < 0.03


def test_measured_alignment_is_one_to_one_when_counts_match():
    x = _speech_with_pauses()
    scenes = [
        {"id": 1, "narration": "الأولى"},
        {"id": 2, "narration": "الثانية"},
        {"id": 3, "narration": "الثالثة"},
    ]
    al = measured_align(scenes, x, RATE, x.shape[1])
    assert al.level == LEVEL_MEASURED
    assert al.segments[0].start_sample == 0
    assert al.segments[2].end_sample == x.shape[1]
    assert all(s.confidence >= 0.8 for s in al.segments)
    # monotonic, no drift
    for a, b in zip(al.segments, al.segments[1:]):
        assert a.end_sample <= b.start_sample


def test_measured_alignment_states_the_mismatch_instead_of_pretending():
    x = _speech_with_pauses()
    scenes = [{"id": 1, "narration": "الأولى"}, {"id": 2, "narration": "الثانية"}]
    al = measured_align(scenes, x, RATE, x.shape[1])
    assert al.level == LEVEL_SEGMENTED
    assert any("≠" in n for n in al.notes)
    assert all(s.confidence < 0.8 for s in al.segments)


def test_measured_alignment_reports_none_for_silence():
    x = np.zeros((1, RATE * 2))
    al = measured_align([{"id": 1, "narration": "شيء"}], x, RATE, x.shape[1])
    assert al.level == LEVEL_NONE
    assert al.segments == []


# --------------------------------------------------------------------------
# narration import + gate
# --------------------------------------------------------------------------
@pytest.fixture()
def project(tmp_path: Path) -> Path:
    pd = tmp_path / "p4"
    (pd / "script").mkdir(parents=True)
    (pd / "research").mkdir()
    (pd / "storyboard").mkdir()
    (pd / "audio").mkdir()
    graph = {
        "lang": "en",
        "scenes": [
            {"id": 1, "narration": "First sentence.", "duration": 4.0},
            {"id": 2, "narration": "Second sentence.", "duration": 4.0},
        ],
    }
    (pd / "script" / "scriptgraph.json").write_text(json.dumps(graph), encoding="utf-8")
    return pd


def _import(project: Path, tmp_path: Path, *, peak_dbfs: float = -20.0) -> Path:
    from engine.audio.narration import import_narration

    src = _write_wav(tmp_path / "voice.wav", _tone(8.0, 1000.0, amp=10 ** (peak_dbfs / 20)))
    import_narration(project, src, copy=True)
    return src


def test_import_stores_relative_paths_and_never_touches_the_source(project: Path, tmp_path: Path):
    src = _import(project, tmp_path)
    before = src.read_bytes()
    manifest = load_narration(project)
    assert manifest is not None
    stored = manifest["stored"]["path"]
    assert stored.startswith("audio/") and stored.endswith(".wav")
    assert not Path(stored).is_absolute()
    assert manifest["original"]["path"] == str(src.resolve())
    assert manifest["original"]["outside_project"] is True
    assert src.read_bytes() == before  # the original is untouched


def test_import_measures_the_loudness(project: Path, tmp_path: Path):
    _import(project, tmp_path, peak_dbfs=-20.0)
    manifest = load_narration(project)
    loud = manifest["loudness"]
    assert loud is not None
    assert loud["lufs_integrated"] == pytest.approx(-23.0, abs=0.6)
    assert loud["true_peak_dbtp"] == pytest.approx(-20.0, abs=0.2)
    assert loud["sample_rate"] == RATE
    assert loud["channels"] == 1


def test_normalization_is_explicit_bounded_and_logged(project: Path, tmp_path: Path):
    _import(project, tmp_path, peak_dbfs=-20.0)
    info = normalize_narration(project, -16.0)
    assert info["gain_db"] == pytest.approx(7.0, abs=0.3)
    assert info["after"]["lufs_integrated"] == pytest.approx(-16.0, abs=0.2)
    assert info["before"]["lufs_integrated"] == pytest.approx(-23.0, abs=0.6)
    manifest = load_narration(project)
    assert manifest["normalization"]["target_lufs"] == -16.0
    assert manifest["loudness"]["lufs_integrated"] == pytest.approx(-16.0, abs=0.2)
    assert (project / manifest["stored"]["path"]).resolve().is_relative_to(project.resolve())


def test_normalization_refuses_an_impossible_gain(project: Path, tmp_path: Path):
    _import(project, tmp_path, peak_dbfs=-40.0)
    with pytest.raises(Exception):
        normalize_narration(project, -16.0)


def test_gate_blocks_a_final_render_with_an_unmeasured_narration(project: Path, tmp_path: Path):
    _import(project, tmp_path)
    manifest = load_narration(project)
    manifest["loudness"] = None
    (project / "audio" / "narration.json").write_text(json.dumps(manifest), encoding="utf-8")
    gate = evaluate_narration_gate(project, {"stats": {"duration": 8.0}}, mode="final")
    assert not gate.ok
    assert gate.blocking[0]["reason"] == "narration-not-measured"
    preview = evaluate_narration_gate(project, {"stats": {"duration": 8.0}}, mode="preview")
    assert preview.ok


def test_gate_blocks_a_narration_shorter_than_the_picture(project: Path, tmp_path: Path):
    _import(project, tmp_path)
    gate = evaluate_narration_gate(project, {"stats": {"duration": 40.0}}, mode="final")
    assert not gate.ok
    assert any(b["reason"] == "narration-shorter-than-picture" for b in gate.blocking)


def test_gate_blocks_an_off_target_narration(project: Path, tmp_path: Path):
    _import(project, tmp_path, peak_dbfs=-20.0)
    gate = evaluate_narration_gate(project, {"stats": {"duration": 8.0}}, mode="final", target_lufs=-16.0)
    assert not gate.ok
    assert any(b["reason"] == "narration-off-target" for b in gate.blocking)


def test_gate_allows_a_measured_on_target_narration(project: Path, tmp_path: Path):
    _import(project, tmp_path, peak_dbfs=-20.0)
    normalize_narration(project, -16.0)
    gate = evaluate_narration_gate(project, {"stats": {"duration": 8.0}}, mode="final", target_lufs=-16.0)
    assert gate.ok, gate.blocking
    assert gate.measured is True
    assert gate.lufs == pytest.approx(-16.0, abs=0.2)


def test_gate_without_narration_is_only_a_warning(project: Path):
    gate = evaluate_narration_gate(project, {"stats": {"duration": 8.0}}, mode="final")
    assert gate.ok
    assert any(w["reason"] == "no-narration" for w in gate.warnings)


def test_resolve_narration_follows_the_project(project: Path, tmp_path: Path):
    _import(project, tmp_path)
    resolved = resolve_narration(project)
    assert resolved.exists()
    assert resolved.parent == (project / "audio").resolve()
