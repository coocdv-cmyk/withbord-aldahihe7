"""العقد: سرد محلي بالكامل — بلا إنترنت وبلا سحابة.

ما كان ناقصًا: ``config.tts`` كان يعلن ``local`` ولا ينفّذه، فكل سرد عربي كان
إما تركيبيًا سحابيًا (Edge) أو مسجَّلًا بشريًّا. هذا الملف يثبت أن المسار
المحلي **منفَّذ ومقيس**:

* ``piper`` مزوّد معلَن ضمن ``BACKENDS`` (لا انزلاق صامت).
* غياب التنفيذ أو النموذج = **خطأ صريح** يشرح ما ينقص (لا ملف صامت).
* المعدّل ``+10%`` ⇒ ``length_scale`` صحيح (Piper: الأطول = الأبطأ).
* التوليد الحقيقي (إن كانت الأدوات مثبَّتة) ينتج WAV بمعدّل المحرّك 48kHz
  أحادي وليس ملفًا فارغًا.
"""
from __future__ import annotations

import wave
from pathlib import Path

import pytest

from engine.audio.tts import (
    BACKENDS,
    TtsConfig,
    TtsError,
    _rate_to_length_scale,
    discover_piper_binary,
    discover_piper_model,
    piper_status,
    synthesize_scene,
)


# --------------------------------------------------------------------------
# العقد: المزوّد معلَن
# --------------------------------------------------------------------------
def test_the_local_backend_is_declared():
    assert "piper" in BACKENDS
    assert "none" in BACKENDS


def test_the_rate_maps_to_the_piper_length_scale():
    # piper: length_scale أكبر = أبطأ ⇒ "+10%" (أسرع) ⇒ 1/1.1
    assert _rate_to_length_scale("+0%") == 1.0
    assert _rate_to_length_scale("+10%") == pytest.approx(1 / 1.1, abs=1e-3)
    assert _rate_to_length_scale("-20%") == pytest.approx(1 / 0.8, abs=1e-3)
    # قيمة مشبوهة لا تُكسر: تبقى 1.0
    assert _rate_to_length_scale("") == 1.0
    assert _rate_to_length_scale("غير رقم") == 1.0


def test_the_config_carries_the_local_model_and_binary(monkeypatch):
    monkeypatch.setenv("RASM_TTS_MODEL", "C:/models/voice.onnx")
    monkeypatch.setenv("RASM_TTS_BINARY", "C:/tools/piper.exe")
    cfg = TtsConfig.from_config(language="ar")
    assert cfg.model_path == "C:/models/voice.onnx"
    assert cfg.binary == "C:/tools/piper.exe"


# --------------------------------------------------------------------------
# العقد: غياب الأدوات خطأ صريح
# --------------------------------------------------------------------------
def test_a_missing_piper_binary_is_an_explicit_error(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("engine.audio.tts.discover_piper_binary", lambda root=None: None)
    with pytest.raises(TtsError) as excinfo:
        synthesize_scene("نص", tmp_path / "s.wav", TtsConfig(backend="piper"))
    assert "runtime/piper" in str(excinfo.value)
    assert not (tmp_path / "s.wav").exists()


def test_a_missing_piper_model_is_an_explicit_error(monkeypatch, tmp_path: Path):
    fake_binary = tmp_path / "piper.exe"
    fake_binary.write_bytes(b"MZ")
    monkeypatch.setattr(
        "engine.audio.tts.discover_piper_binary", lambda root=None: fake_binary
    )
    monkeypatch.setattr("engine.audio.tts.discover_piper_model", lambda language="ar", root=None: None)
    with pytest.raises(TtsError) as excinfo:
        synthesize_scene("نص", tmp_path / "s.wav", TtsConfig(backend="piper"))
    assert "tts-models" in str(excinfo.value)
    assert not (tmp_path / "s.wav").exists()


# --------------------------------------------------------------------------
# المسار الحقيقي (يتخطّى إن لم تكن الأدوات مثبَّتة)
# --------------------------------------------------------------------------
requires_piper = pytest.mark.skipif(
    not (discover_piper_binary() and discover_piper_model("ar")),
    reason="Piper المحلي غير مثبَّت على هذا الجهاز",
)


@requires_piper
def test_the_local_path_generates_a_real_narration(tmp_path: Path):
    """حقيقة مقيسة: الصوت المولَّد عربي فعلي بمعدّل 48kHz وليس ملفًا فارغًا."""
    out = tmp_path / "scene.wav"
    synthesize_scene("بدأت الحرب العالمية الأولى عام ألف وتسعمئة وأربعة عشر.", out, TtsConfig(backend="piper"))
    assert out.exists()
    with wave.open(str(out), "rb") as w:
        assert w.getframerate() == 48000
        assert w.getnchannels() == 1
        frames = w.getnframes()
        data = w.readframes(frames)
    assert frames > 48000  # أكثر من ثانية: ليس ملفًا صامتًا
    assert any(b != 0 for b in data)


@requires_piper
def test_the_status_reports_the_local_tools():
    status = piper_status("ar")
    assert status["available"] is True
    assert status["backend"] == "piper"
    assert Path(status["binary"]).exists()
    assert Path(status["model"]).exists()
    assert status["model_bytes"] > 1_000_000
