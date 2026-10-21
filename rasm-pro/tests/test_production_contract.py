"""The production contract shared by the CLI and Studio.

A production render is only allowed when the **actual** audio file matches its
manifest, the alignment still describes the active plan, the SFX library is
complete, every scene fits, and the written file passes FFprobe.  These tests
exercise the shared module directly; the CLI and Studio both call it.
"""
from __future__ import annotations

import json
import math
import struct
import wave
from pathlib import Path

import pytest

from engine.audio import import_narration, save_alignment
from engine.audio.align import baseline_align
from engine.audio.narration import load_narration, normalize_narration, resolve_narration
from engine.audio.probe import sha256_file
from engine.production import prepare_production, render_production
from engine.render.director import RenderPreflightError

from conftest import requires_ffmpeg, requires_ffprobe

RATE = 16000


def _make_speech_wav(path: Path, total_seconds: float = 5.0) -> Path:
    """Three tone bursts with real pauses (so VAD has something to measure)."""
    pattern = [(1.2, 320.0), (0.5, 0.0), (1.2, 320.0), (0.5, 0.0), (1.6, 320.0)]
    assert sum(d for d, _ in pattern) == pytest.approx(total_seconds)
    data = bytearray()
    for seconds, freq in pattern:
        n = int(round(seconds * RATE))
        for i in range(n):
            value = int(9000 * math.sin(2 * math.pi * freq * i / RATE)) if freq else 0
            data += struct.pack("<h", value)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(bytes(data))
    return path


def _plan(narration: tuple[str, str] = ("الجملة الأولى", "الجملة الثانية")) -> dict:
    return {
        "fps": {"num": 24, "den": 1},
        "canvas": [320, 180],
        "family": {"motion": {"zoom": 1.8, "follow": 0.07}},
        "scenes": [
            {
                "id": i + 1,
                "narration": text,
                "duration": 2.5,
                "start_frame": i * 60,
                "end_frame": (i + 1) * 60,
                "duration_frames": 60,
                "elements": [
                    {
                        "type": "text",
                        "text": text,
                        "font": "inter",
                        "size": 40,
                        "rect": [20, 20, 280, 100],
                        "mode": "skeleton",
                        "rtl": True,
                        "color": "#211E1A",
                        "gap": 0.2,
                    }
                ],
            }
            for i, text in enumerate(narration)
        ],
        "timebase": {"start_frame": 0, "end_frame": 120, "frames": 120},
        "stats": {"scenes": 2, "elements": 2, "duration": 5.0, "estimated_duration": 5.0},
    }


def _project_with_narration(tmp_path: Path) -> tuple[Path, dict, dict]:
    pd = tmp_path / "project"
    (pd / "storyboard").mkdir(parents=True)
    (pd / "audio").mkdir()
    src = _make_speech_wav(tmp_path / "speech.wav")
    import_narration(pd, src, note="test")
    normalize_narration(pd, -16.0)
    plan = _plan()
    silence = 0
    nar = load_narration(pd)
    assert nar is not None
    al = baseline_align(plan["scenes"], int(nar["total_samples"]), int(nar["sample_rate"]))
    save_alignment(al, pd)
    plan["audio"] = {
        "file": nar["path"],
        "sha256": nar["sha256"],
        "total_samples": nar["total_samples"],
        "sample_rate": nar["sample_rate"],
    }
    (pd / "storyboard" / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
    return pd, plan, nar


def test_prepare_accepts_measured_audio_and_current_alignment(tmp_path: Path):
    pd, plan, _nar = _project_with_narration(tmp_path)
    prep = prepare_production(
        pd,
        plan,
        mode="final",
        size=(160, 90),
        sfx=False,
        target_lufs=-16.0,
    )
    assert prep.ok, prep.blocking
    assert prep.audio["actual_sha256"] == prep.audio["manifest_sha256"]
    assert prep.alignment["ok"] is True
    assert prep.audio_file is not None
    assert prep.director is not None


def test_prepare_blocks_when_the_audio_bytes_changed(tmp_path: Path):
    pd, plan, _nar = _project_with_narration(tmp_path)
    stored = resolve_narration(pd)
    raw = bytearray(stored.read_bytes())
    # Flip one byte in the PCM data, keeping a valid WAV that ffprobe can read.
    raw[-8] ^= 0x01
    stored.write_bytes(bytes(raw))

    prep = prepare_production(
        pd, plan, mode="final", size=(160, 90), sfx=False, target_lufs=-16.0
    )
    assert not prep.ok
    assert any(b["reason"] == "narration-hash-mismatch" for b in prep.blocking)


def test_prepare_blocks_when_the_alignment_no_longer_matches_the_plan(tmp_path: Path):
    pd, plan, _nar = _project_with_narration(tmp_path)
    ap = pd / "audio" / "alignment.json"
    data = json.loads(ap.read_text(encoding="utf-8"))
    data["segments"][0]["text"] = "نص قديم لا يطابق الخطة"
    ap.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    prep = prepare_production(
        pd, plan, mode="final", size=(160, 90), sfx=False, target_lufs=-16.0
    )
    assert not prep.ok
    assert any(b["reason"] == "alignment-stale" for b in prep.blocking)


@requires_ffmpeg
@requires_ffprobe
def test_final_render_uses_the_contract_and_validates_the_written_file(tmp_path: Path):
    pd = tmp_path / "silent-project"
    (pd / "storyboard").mkdir(parents=True)
    plan = _plan(("Hello", "World"))
    plan["audio"] = None
    plan["stats"]["duration"] = 2.5
    plan["scenes"] = plan["scenes"][:1]
    plan["scenes"][0]["end_frame"] = 60
    plan["scenes"][0]["duration_frames"] = 60
    # No narration in this project: a final render is still allowed, with SFX.
    result = render_production(
        pd,
        plan,
        mode="final",
        size=(160, 90),
        sfx=True,
        target_lufs=-16.0,
    )
    assert result["ok"], result.get("production")
    assert result["production"]["validation"]["ok"]
    assert result["production"]["mix"]["mode"] == "sfx-only"
    assert Path(result["mix_report"]).exists()
    assert result["audio_start_sec"] == 0.0


def test_preflight_refusal_is_reported_before_the_file_exists(tmp_path: Path):
    pd = tmp_path / "impossible"
    (pd / "storyboard").mkdir(parents=True)
    plan = _plan()
    for index, scene in enumerate(plan["scenes"]):
        scene["duration"] = 0.5
        scene["start_frame"] = index * 12
        scene["end_frame"] = scene["start_frame"] + 12
        scene["duration_frames"] = 12
        scene["elements"] = [
            {"type": "paper_card", "rect": [10, 10, 100, 60], "reveal_time": 0.4, "gap": 0.2}
            for _ in range(4)
        ]
    out = tmp_path / "must-not-exist.mp4"
    with pytest.raises(RenderPreflightError):
        render_production(
            pd,
            plan,
            mode="final",
            size=(160, 90),
            sfx=False,
            out_path=out,
        )
    assert not out.exists()
