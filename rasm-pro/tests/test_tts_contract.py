"""Regression: توليد السرد داخل المحرك يجب أن يكون **مزوّدًا معلنًا صريحًا**.

ما كان ناقصًا: ``config.tts`` كان يعلن أربعة مزوّدين ولا ينفّذ أيًّا منهم، فكانت
«حلقة بلا سرد» نتيجة بنية. هذه الاختبارات تثبت العقد الجديد:

* مزوّد واحد معلن — ``none`` يرفض بوضوح، ولا مزوّد مجهول ولا ملف صامت.
* الصمتات **مقيسة بالعينات** (لا تقدير) والـ lead-in قبل أول كلمة لا بعدها.
* الملف المولَّد **يُستورد** ويُقاس ويُسجَّل بأصله (مزوّد + صوت + معدّل).
* كل عطل (حزمة ناقصة، مزوّد مجهول) خطأ صريح — بلا شبكة في الاختبار.
"""
from __future__ import annotations

import math
import struct
import sys
import wave
from argparse import Namespace
from pathlib import Path

import pytest

from engine.audio.tts import (
    TtsConfig,
    TtsError,
    assemble_narration,
    default_voice,
    scene_words,
    split_script,
    synthesize_narration,
    synthesize_project,
)


def _tone_wav(path: Path, seconds: float = 0.5, freq: float = 220.0, sr: int = 48000) -> Path:
    n = int(seconds * sr)
    buf = bytearray()
    for i in range(n):
        v = int(0.1 * 32767 * math.sin(2 * math.pi * freq * i / sr))
        buf += struct.pack("<h", v)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(bytes(buf))
    return path


# --------------------------------------------------------------------------
# العقد: مزوّد معلن، وأخطاء صريحة
# --------------------------------------------------------------------------
def test_backend_none_refuses_instead_of_writing_a_silent_file(tmp_path: Path):
    out = tmp_path / "scene.wav"
    with pytest.raises(TtsError) as excinfo:
        from engine.audio.tts import synthesize_scene

        synthesize_scene("نص", out, TtsConfig(backend="none"))
    assert "edge" in str(excinfo.value)  # يذكر الخيارات المتاحة
    assert not out.exists()


def test_an_unknown_backend_is_refused(tmp_path: Path):
    with pytest.raises(TtsError) as excinfo:
        from engine.audio.tts import synthesize_scene

        synthesize_scene("نص", tmp_path / "s.wav", TtsConfig(backend="elevenlabs"))
    assert "غير معروف" in str(excinfo.value)


def test_a_missing_edge_package_is_an_explicit_error(monkeypatch, tmp_path: Path):
    monkeypatch.setitem(sys.modules, "edge_tts", None)
    with pytest.raises(TtsError) as excinfo:
        from engine.audio.tts import synthesize_scene

        synthesize_scene("نص", tmp_path / "s.wav", TtsConfig(backend="edge"))
    assert "edge-tts" in str(excinfo.value)


def test_azure_without_a_key_is_refused(tmp_path: Path):
    with pytest.raises(TtsError) as excinfo:
        from engine.audio.tts import synthesize_scene

        synthesize_scene("نص", tmp_path / "s.wav", TtsConfig(backend="azure"))
    assert "AZURE" in str(excinfo.value) or "مفتاح" in str(excinfo.value)


# --------------------------------------------------------------------------
# Voices and configuration
# --------------------------------------------------------------------------
def test_the_default_voice_follows_the_language():
    assert default_voice("ar") == "ar-EG-ShakirNeural"
    assert default_voice("en") == "en-US-AriaNeural"
    cfg = TtsConfig(backend="edge", language="ar")
    assert cfg.resolved_voice() == "ar-EG-ShakirNeural"
    cfg.voice = "ar-EG-MonotonicNeural"
    assert cfg.resolved_voice() == "ar-EG-MonotonicNeural"


def test_the_environment_overrides_the_configured_backend(monkeypatch):
    monkeypatch.setenv("RASM_TTS_BACKEND", "azure")
    monkeypatch.setenv("RASM_TTS_VOICE", "ar-EG-SalmaNeural")
    cfg = TtsConfig.from_config(language="ar")
    assert cfg.backend == "azure"
    assert cfg.resolved_voice() == "ar-EG-SalmaNeural"


# --------------------------------------------------------------------------
# Script splitting
# --------------------------------------------------------------------------
def test_a_script_is_split_into_scenes_by_blank_lines_and_rules():
    text = "المشهد الأول.\n\nالمشهد الثاني.\n\n---\n\nالمشهد الثالث."
    scenes = split_script(text)
    assert scenes == ["المشهد الأول.", "المشهد الثاني.", "المشهد الثالث."]
    assert scene_words(scenes) == 6
    assert split_script("   ") == []


# --------------------------------------------------------------------------
# Assembly: measured silences, lead-in first
# --------------------------------------------------------------------------
def test_the_assembly_measures_the_pauses_and_puts_the_lead_in_first(tmp_path: Path):
    a = _tone_wav(tmp_path / "a.wav", 1.0)
    b = _tone_wav(tmp_path / "b.wav", 1.0)
    out = tmp_path / "narration.wav"
    report = assemble_narration([a, b], out, pauses=0.5, lead_in=0.25)
    # 1s + 1s of speech + one 0.5s pause + a 0.25s lead-in
    assert report["total_samples"] == 48000 * 2 + 24000 + 12000
    assert report["duration_sec"] == round((48000 * 2 + 24000 + 12000) / 48000, 6)
    with wave.open(str(out), "rb") as w:
        data = w.readframes(w.getnframes())
    samples = struct.unpack(f"<{len(data)//2}h", data)
    # the lead-in is silence BEFORE the first word
    assert all(v == 0 for v in samples[:12000])
    assert any(v != 0 for v in samples[12000:60000])
    # the pause between the scenes is real silence
    assert all(v == 0 for v in samples[48000 + 12000: 48000 + 12000 + 24000])


def test_the_assembly_refuses_an_empty_scene_list(tmp_path: Path):
    with pytest.raises(TtsError):
        assemble_narration([], tmp_path / "n.wav")


# --------------------------------------------------------------------------
# The full path: generate → import → describe
# --------------------------------------------------------------------------
def test_the_project_path_generates_imports_and_records_the_origin(tmp_path: Path):
    project = tmp_path / "demo"
    (project / "audio").mkdir(parents=True)

    def fake_synth(text: str, out_wav: Path, cfg: TtsConfig, *, work_dir=None) -> Path:
        return _tone_wav(out_wav, 0.5, freq=200.0 + 10 * len(text))

    report = synthesize_project(
        project,
        ["المشهد الأول", "المشهد الثاني"],
        cfg=TtsConfig(backend="edge", voice="ar-EG-ShakirNeural"),
        pauses=0.4,
        lead_in=0.2,
        synthesizer=fake_synth,
    )
    assert report["scenes"] == 2
    assert report["backend"] == "edge"
    assert report["voice"] == "ar-EG-ShakirNeural"

    man = report["manifest"]
    assert man["original"]["generated_by"] == "engine.tts"
    assert man["original"]["outside_project"] is False
    assert man["original"]["backend"] == "edge"
    # the stored copy lives inside the project (relative path)
    assert not Path(man["path"]).is_absolute()
    assert (project / man["path"]).exists()
    # the measured loudness of the generated file is part of the description
    assert man.get("loudness") is not None
    assert man["total_samples"] > 0


def test_the_synthesizer_can_be_injected_for_every_scene(tmp_path: Path):
    calls: list[str] = []

    def fake_synth(text: str, out_wav: Path, cfg: TtsConfig, *, work_dir=None) -> Path:
        calls.append(text)
        return _tone_wav(out_wav, 0.25)

    report = synthesize_narration(
        ["أ", "ب", "ج"],
        tmp_path / "n.wav",
        TtsConfig(backend="edge"),
        pauses=0.1,
        lead_in=0.0,
        synthesizer=fake_synth,
    )
    assert calls == ["أ", "ب", "ج"]
    assert report["scene_samples"] == [12000, 12000, 12000]
    # one gap between the scenes — no trailing silence after the last scene
    assert report["pause_samples"] == [4800, 4800]
    assert report["total_samples"] == 3 * 12000 + 2 * 4800


# --------------------------------------------------------------------------
# The CLI refuses when there is nothing to speak
# --------------------------------------------------------------------------
def test_the_cli_refuses_when_there_are_no_scenes(tmp_path: Path, capsys):
    from rasm import cmd_tts

    project = tmp_path / "empty"
    project.mkdir()
    args = Namespace(
        project=str(project),
        script=None,
        backend="edge",
        voice=None,
        rate=None,
        pitch=None,
        pause=None,
        lead_in=0.35,
        lang="ar",
        dry_run=False,
    )
    assert cmd_tts(args) == 2
    assert "لا مشاهد" in capsys.readouterr().err


def test_the_cli_dry_run_never_touches_the_network(tmp_path: Path, capsys):
    from rasm import cmd_tts

    project = tmp_path / "demo"
    (project / "script").mkdir(parents=True)
    (project / "script" / "scriptgraph.json").write_text(
        '{"lang": "ar", "scenes": [{"id": 1, "narration": "مشهد واحد."}, {"id": 2, "narration": "مشهد اثنان."}]}',
        encoding="utf-8",
    )
    args = Namespace(
        project=str(project),
        script=None,
        backend="edge",
        voice=None,
        rate=None,
        pitch=None,
        pause=None,
        lead_in=0.35,
        lang="ar",
        dry_run=True,
    )
    assert cmd_tts(args) == 0
    out = capsys.readouterr().out
    assert "edge" in out
    assert "dry-run" in out
    # no narration was generated: no audio files, no tts folder
    assert not (project / "audio" / "tts").exists()
    assert not list(project.glob("audio/*.wav"))
