"""العقد: المحاذاة على مستوى **الكلمة** — مقيسة من التسجيل نفسه.

ما كان ناقصًا: مستوى ``SEGMENTED`` (0.55) يوزّع الجمل **تقديريًّا** على زمن
النطق المقيس، فلا كلمة لها زمن، فلا شفاه ولا إبراز. المستوى ``WORD`` كان
معلَنًا في العقد بلا تنفيذ.

هذه الاختبارات تثبت التنفيذ الجديد:

* ``word_align`` يبني حدود المشاهد من **كلمات مفرَّغة** لا من تقدير.
* المشهد الذي لا تُطابق كلماته يُعلَّم ``unmatched`` — لا يُدّعى أنه مضبوط.
* المخرجات **متّصلة**: من العيّنة صفر إلى نهاية الصوت (شرط عقد الإنتاج).
* محلّل رموز whisper.cpp يجمع الرموز في كلمات بتوقيتاتها.
* المسار الحقيقي (whisper.cpp محلي) يُنتج كلمات بتوقيتات — إن وُجدت الأدوات.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from engine.audio.align import LEVEL_WORD, WordTiming, word_align
from engine.audio.asr import (
    AsrError,
    asr_status,
    parse_whisper_tokens,
    transcript_words,
)


def _scenes(*texts: str) -> list[dict]:
    return [{"id": i + 1, "narration": t} for i, t in enumerate(texts)]


def _words(pairs: list[tuple[str, float, float]]) -> list[WordTiming]:
    return [WordTiming(text=t, start_sec=a, end_sec=b, prob=0.9) for t, a, b in pairs]


# --------------------------------------------------------------------------
# المحاذاة: من الكلمات إلى حدود المشاهد
# --------------------------------------------------------------------------
def test_the_scene_boundaries_come_from_the_measured_words():
    sr = 1000  # عيّنة/ثانية (تبسيط: الأعداد مقروءة)
    total = 10_000
    scenes = _scenes("بدأت الحرب", "وانتهت بعد عام")
    words = _words(
        [
            ("بدأت", 0.0, 1.0),
            ("الحرب", 1.0, 2.0),
            ("وانتهت", 6.0, 7.0),
            ("بعد", 7.0, 7.5),
            ("عام", 7.5, 8.0),
        ]
    )
    al = word_align(scenes, words, sample_rate=sr, total_samples=total)
    assert al.level == LEVEL_WORD
    assert al.method == "asr-word-timed-v1"
    first, second = al.segments
    # حدود المشهد تُشتق من أوقات الكلمات المقيسة: آخر كلمة في المشهد الأول
    # انتهت عند 2.0ث، وأول كلمة في الثاني بدأت عند 6.0ث ⇒ الحدّ في منتصف
    # الصمت بينهما (4.0ث) — لا تقدير عن طول النص.
    assert first.end_sample == 4000
    assert second.start_sample == 4000
    assert all(seg.flags and "asr-word-timed" in seg.flags for seg in al.segments)


def test_an_unmatched_scene_is_flagged_instead_of_being_claimed_exact():
    scenes = _scenes("كلمة موجودة", "كلمة لم تُقل في التسجيل أبدا")
    words = _words([("كلمة", 0.0, 1.0), ("موجودة", 1.0, 2.0)])
    al = word_align(scenes, words, sample_rate=1000, total_samples=5000)
    assert "unmatched" in al.segments[1].flags
    assert al.segments[1].confidence <= 0.4
    assert any("مطابقة" in note for note in al.notes)


def test_the_alignment_covers_the_whole_recording_without_gaps():
    """شرط عقد الإنتاج: متّصلة من 0 إلى النهاية، وكل مشهد له مدّة."""
    scenes = _scenes("أ", "ب", "ج")
    words = _words([("أ", 0.0, 1.0), ("ب", 2.0, 3.0), ("ج", 4.0, 5.0)])
    al = word_align(scenes, words, sample_rate=1000, total_samples=6000)
    starts = [s.start_sample for s in al.segments]
    ends = [s.end_sample for s in al.segments]
    assert starts[0] == 0
    assert ends[-1] == 6000
    assert all(end == nxt for end, nxt in zip(ends, starts[1:]))
    assert all(end > start for start, end in zip(starts, ends))


def test_an_empty_transcript_refuses_instead_of_guessing():
    """بلا كلمات ⇒ لا محاذاة (المستوى NONE) — لا توزيع تقديري متخفٍّ."""
    al = word_align(_scenes("أ"), [], sample_rate=1000, total_samples=1000)
    assert al.level == "NONE"
    assert al.segments == []
    assert al.notes


def test_a_zero_length_recording_is_refused():
    with pytest.raises(Exception):
        word_align(_scenes("أ"), _words([("أ", 0.0, 1.0)]), sample_rate=1000, total_samples=0)


# --------------------------------------------------------------------------
# محلّل مخرجات whisper.cpp
# --------------------------------------------------------------------------
def test_the_token_parser_groups_tokens_into_words_with_their_times():
    payload = {
        "transcription": [
            {
                "tokens": [
                    {"text": "[_BEG_]", "offsets": {"from": 0, "to": 0}, "p": 0.9},
                    {"text": " مر", "offsets": {"from": 100, "to": 200}, "p": 0.8},
                    {"text": "حب", "offsets": {"from": 200, "to": 300}, "p": 0.7},
                    {"text": "!", "offsets": {"from": 300, "to": 350}, "p": 0.6},
                    {"text": " عام", "offsets": {"from": 900, "to": 1000}, "p": 0.9},
                    {"text": "[_TT_530]", "offsets": {"from": 1060, "to": 1060}, "p": 0.1},
                ]
            }
        ]
    }
    words, segments = parse_whisper_tokens(payload)
    assert segments == 1
    assert [w.text for w in words] == ["مرحب!", "عام"]
    assert words[0].start_sec == pytest.approx(0.1)
    assert words[0].end_sec == pytest.approx(0.35)
    assert words[1].start_sec == pytest.approx(0.9)
    assert words[0].prob == pytest.approx(0.7)


def test_the_transcript_words_round_trip():
    payload = {
        "words": [
            {"text": "أ", "start_sec": 0.0, "end_sec": 1.0, "prob": 0.8},
            {"text": "ب", "start_sec": 1.0, "end_sec": 2.0, "prob": 0.7},
        ]
    }
    words = transcript_words(payload)
    assert [w.text for w in words] == ["أ", "ب"]
    assert words[1].end_sec == 2.0


def test_an_unknown_backend_is_refused_explicitly(tmp_path: Path):
    from engine.audio.asr import transcribe

    with pytest.raises(AsrError) as excinfo:
        transcribe(tmp_path / "nope.wav", backend="nope")
    assert "غير معروف" in str(excinfo.value)


# --------------------------------------------------------------------------
# المسار الحقيقي (يتخطّى إن لم تكن الأدوات مثبَّتة)
# --------------------------------------------------------------------------
requires_asr = pytest.mark.skipif(
    not asr_status().get("available"),
    reason="whisper.cpp المحلي غير مثبَّت على هذا الجهاز",
)


@requires_asr
def test_the_local_transcriber_gives_word_times(tmp_path: Path):
    """حقيقة مقيسة: تفريغ محلي لكلمات بتوقيتاتها — بلا سحابة."""
    import wave

    from engine.audio.asr import transcribe

    # صوت كلام حقيقي من Piper (إن وُجد) — لا صوت مركّب: التفريغ يحتاج كلامًا
    from engine.audio.tts import TtsConfig, discover_piper_binary, discover_piper_model, synthesize_scene

    if not (discover_piper_binary() and discover_piper_model("ar")):
        pytest.skip("Piper غير مثبَّت")
    wav = synthesize_scene(
        "بدأت الحرب العالمية الأولى عام ألف وتسعمئة وأربعة عشر.",
        tmp_path / "speech.wav",
        TtsConfig(backend="piper"),
    )
    transcript = transcribe(wav, language="ar")
    assert transcript.words, "لم تُستخرج كلمات من تسجيل واضح"
    assert all(w.end_sec >= w.start_sec for w in transcript.words)
    assert transcript.duration_sec > 1.0
