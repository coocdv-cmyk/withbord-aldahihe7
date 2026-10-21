"""توليد السرد داخل المحرك (TTS) — مزوّدات حقيقية خلف عقد ``config.tts``.

لماذا هذا الملف موجود
---------------------
كان ``config.json`` يعلن ``tts.backend: none | edge | azure | elevenlabs | local``
ولم يكن هناك **أي تنفيذ** لأحدها: السرد كان يُستورد من ملف خارجي فقط، أي أن
«حلقة بلا سرد» كانت نتيجة بنية لا خيارًا. هذا الملف يجعل التوليد **جزءًا من
العقد** بنفس القواعد:

* مزوّد واحد معلن فقط — لا انزلاق صامت إلى مزوّد آخر ولا إلى مولّد محلّي.
* كل عطل يُرفع كخطأ صريح (حزمة ناقصة، مفتاح ناقص، انقطاع شبكة) — لا ملف صامت.
* الخرج **ملف سرد عادي**: يمرّ على ``import_narration`` ⇒ قياس جهارة ⇒ محاذاة
  ⇒ بوابة الصوت، فتسري عليه القواعد نفسها على أي سرد مستورد.
* تُسجَّل **أصلية** التوليد في ``audio/narration.json`` (المزوّد، الصوت، المعدّل)
  حتى يعرف الفحص اللاحق أن هذا الصوت مُولَّد لا مُسجَّل بشريًّا.

المصطلحات
---------
``scenes``         قائمة نصوص، كل نص = مشهد صوتي واحد.
``pause``          صمت مُقاس بين المشاهد (بالثواني) — لا تقدير: يُحسب بالعينات.
``lead_in``        صمت قبل أول كلمة حتى لا تبدأ عند حافة الملف.
"""
from __future__ import annotations

import asyncio
import os
import re
import subprocess
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Sequence

from ..core.log import get_logger
from .narration import import_narration

log = get_logger("audio.tts")

SAMPLE_RATE = 48000
SAMPLE_WIDTH = 2
CHANNELS = 1
DEFAULT_VOICES = {
    "ar": "ar-EG-ShakirNeural",
    "en": "en-US-AriaNeural",
}
BACKENDS = ("none", "edge", "azure")


class TtsError(RuntimeError):
    """تعذّر توليد السرد — يُرفع كخطأ صريح، لا كملف صامت."""


# --------------------------------------------------------------------------
# الإعدادات
# --------------------------------------------------------------------------
@dataclass
class TtsConfig:
    """عقد إعداد واحد يحدّد المزوّد والصوت والمعدّلات."""

    backend: str = "none"
    voice: str = ""
    rate: str = "+0%"
    pitch: str = "+0Hz"
    sample_rate: int = SAMPLE_RATE
    timeout_s: int = 120
    api_key: str = ""
    region: str = ""
    language: str = "ar"

    @classmethod
    def from_config(cls, config=None, *, language: str = "ar") -> "TtsConfig":
        """يقرأ عقد ``tts`` من الإعدادات + متغيرات البيئة."""
        from ..core.config import load_config

        cfg = config or load_config()
        backend = (os.environ.get("RASM_TTS_BACKEND") or cfg.get("tts", "backend", default="none") or "none")
        backend = str(backend).strip().lower()
        voice = os.environ.get("RASM_TTS_VOICE") or cfg.get("tts", "voice", default="") or ""
        rate = os.environ.get("RASM_TTS_RATE") or cfg.get("tts", "rate", default="+0%") or "+0%"
        pitch = os.environ.get("RASM_TTS_PITCH") or cfg.get("tts", "pitch", default="+0Hz") or "+0Hz"
        sample_rate = int(
            os.environ.get("RASM_TTS_SAMPLE_RATE")
            or cfg.get("tts", "sample_rate", default=SAMPLE_RATE)
            or SAMPLE_RATE
        )
        api_key = (
            os.environ.get("RASM_TTS_API_KEY")
            or os.environ.get("AZURE_SPEECH_KEY")
            or cfg.get("tts", "api_key", default="")
            or ""
        )
        region = (
            os.environ.get("RASM_TTS_REGION")
            or os.environ.get("AZURE_SPEECH_REGION")
            or cfg.get("tts", "region", default="")
            or ""
        )
        return cls(
            backend=backend,
            voice=str(voice),
            rate=str(rate),
            pitch=str(pitch),
            sample_rate=sample_rate,
            api_key=str(api_key),
            region=str(region),
            language=str(language or "ar"),
        )

    def resolved_voice(self) -> str:
        """الصوت الفعلي: المعلن، وإلا صوت اللغة الافتراضي."""
        if self.voice:
            return self.voice
        return DEFAULT_VOICES.get(self.language.split("-")[0].lower(), DEFAULT_VOICES["en"])


def default_voice(language: str) -> str:
    """الصوت الافتراضي للّغة (ar-EG-ShakirNeural / en-US-AriaNeural)."""
    return DEFAULT_VOICES.get(
        str(language or "ar").split("-")[0].lower(), DEFAULT_VOICES["en"]
    )


# --------------------------------------------------------------------------
# تقسيم السكريبت إلى مشاهد
# --------------------------------------------------------------------------
_SPLIT_RE = re.compile(
    r"(?:\r?\n){2,}|(?:\r?\n)[ \t]*(?:---+|\*\*\*+)[ \t]*(?:\r?\n|$)|^[ \t]*---+[ \t]*$",
    re.MULTILINE,
)


def split_script(text: str) -> list[str]:
    """يفصل نصًّا إلى مشاهد: فقرة فارغة أو سطر ``---`` = مشهد.

    كل نص يُنظَّف (أسطر متعدّدة تُدمج بمسافة) لأن المحرك يقيس الكلمات.
    """
    if not (text or "").strip():
        return []
    out: list[str] = []
    for block in _SPLIT_RE.split(text):
        cleaned = " ".join(line.strip() for line in block.splitlines() if line.strip())
        cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
        if cleaned:
            out.append(cleaned)
    return out


def scene_words(scenes: Sequence[str]) -> int:
    """عدد كلمات المشاهد (المقياس الوحيد لطول الكلام)."""
    return sum(len(str(s or "").split()) for s in scenes)


# --------------------------------------------------------------------------
# المزوّدات
# --------------------------------------------------------------------------
def _ffmpeg() -> str:
    from ..render.video import require_ffmpeg

    return require_ffmpeg()


def _to_wav(src: Path, dst: Path, *, sample_rate: int = SAMPLE_RATE) -> Path:
    """يحوّل أي صوت إلى WAV PCM16 أحادي 48k (المقياس الوحيد للمحرك)."""
    exe = _ffmpeg()
    cmd = [
        exe, "-y", "-v", "error", "-i", str(src),
        "-ac", str(CHANNELS), "-ar", str(sample_rate), "-c:a", "pcm_s16le", str(dst),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise TtsError(f"فشل تحويل الصوت إلى WAV: {proc.stderr[-300:]}")
    return dst


def _synth_edge(text: str, out_mp3: Path, cfg: TtsConfig) -> Path:
    """Microsoft Edge TTS (حزمة ``edge-tts`` اختيارية — تحتاج إنترنت)."""
    try:
        import edge_tts  # noqa: PLC0415
    except ImportError as exc:
        raise TtsError(
            "حزمة edge-tts غير مثبّتة. ثبّتها: "
            "rasm-pro\\.venv\\Scripts\\python.exe -m pip install edge-tts"
        ) from exc

    voice = cfg.resolved_voice()

    async def _run() -> None:
        comm = edge_tts.Communicate(text, voice, rate=cfg.rate, pitch=cfg.pitch)
        await comm.save(str(out_mp3))

    try:
        asyncio.run(_run())
    except Exception as exc:  # network / voice errors
        raise TtsError(f"فشل التوليد عبر Edge TTS (الصوت {voice}): {exc}") from exc
    if not out_mp3.exists() or out_mp3.stat().st_size == 0:
        raise TtsError(f"لم يُنتج Edge TTS أي صوت للصوت {voice}")
    return out_mp3


def _synth_azure(text: str, out_mp3: Path, cfg: TtsConfig) -> Path:
    """Azure Neural TTS (مفتاح + منطقة) — نفس عقد الـ SSML."""
    if not cfg.api_key or not cfg.region:
        raise TtsError(
            "مزوّد Azure يحتاج مفتاحًا ومنطقة: "
            "AZURE_SPEECH_KEY + AZURE_SPEECH_REGION (أو RASM_TTS_API_KEY + RASM_TTS_REGION)"
        )
    import requests  # noqa: PLC0415

    voice = cfg.resolved_voice()
    ssml = (
        "<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='en-US'>"
        f"<voice name='{voice}'>"
        f"<prosody rate='{cfg.rate}' pitch='{cfg.pitch}'>{_escape_ssml(text)}</prosody>"
        "</voice></speak>"
    )
    url = f"https://{cfg.region}.tts.speech.microsoft.com/cognitiveservices/v1"
    headers = {
        "Ocp-Apim-Subscription-Key": cfg.api_key,
        "Content-Type": "application/ssml+xml",
        "X-Microsoft-OutputFormat": "audio-24khz-48kbitrate-mono-mp3",
        "User-Agent": "rasm-pro",
    }
    try:
        resp = requests.post(url, headers=headers, data=ssml.encode("utf-8"), timeout=cfg.timeout_s)
    except Exception as exc:
        raise TtsError(f"فشل الاتصال بمزوّد Azure: {exc}") from exc
    if resp.status_code != 200:
        raise TtsError(f"رفض Azure الطلب ({resp.status_code}): {resp.text[:200]}")
    out_mp3.write_bytes(resp.content)
    return out_mp3


def _escape_ssml(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def synthesize_scene(
    text: str,
    out_wav: Path,
    cfg: TtsConfig,
    *,
    work_dir: Path | None = None,
) -> Path:
    """يولّد مشهدًا واحدًا إلى WAV PCM16 أحادي 48k."""
    if not str(text or "").strip():
        raise TtsError("نص المشهد فارغ — لا صوت يُولَّد")
    backend = cfg.backend
    if backend == "none":
        raise TtsError(
            "لا مزوّد TTS مفعَّل. اختر واحدًا: "
            "rasm tts <project> --backend edge   (أو azure بعد ضبط المفتاح والمنطقة)"
        )
    if backend not in BACKENDS:
        raise TtsError(f"مزوّد TTS غير معروف: {backend!r} — المتاح: {', '.join(BACKENDS)}")
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    tmp = work_dir or out_wav.parent
    tmp.mkdir(parents=True, exist_ok=True)
    mp3 = tmp / (out_wav.stem + ".mp3")
    if backend == "edge":
        _synth_edge(text, mp3, cfg)
    else:
        _synth_azure(text, mp3, cfg)
    return _to_wav(mp3, out_wav, sample_rate=cfg.sample_rate)


# --------------------------------------------------------------------------
# التجميع (بعيّنات — لا تقدير)
# --------------------------------------------------------------------------
def assemble_narration(
    scene_wavs: Sequence[Path],
    out_wav: Path,
    *,
    pauses: Sequence[float] | float = 0.8,
    lead_in: float = 0.35,
) -> dict:
    """يلصق مشاهد WAV بصمتات **مقيسة** بينها.

    ``pauses`` إما عدد واحد لكل الفواصل أو قائمة فاصلة لكل فاصل.
    الفواصل **بين المشاهد فقط** (لا صمت بعد آخر مشهد)، والـ lead-in قبل أول
    كلمة.  الصمت يُكتب كأصفار (لا ضجيج) حتى يبقى صمتًا حقيقيًا في القياس.
    """
    if not scene_wavs:
        raise TtsError("لا مشاهد لتجميعها")
    gaps_count = max(0, len(scene_wavs) - 1)
    if isinstance(pauses, (int, float)):
        pause_list = [float(pauses)] * gaps_count
    else:
        pause_list = [float(p) for p in pauses][:gaps_count]
        if len(pause_list) < gaps_count:
            pause_list += [pause_list[-1] if pause_list else 0.8] * (gaps_count - len(pause_list))
    lead_samples = max(0, int(round(float(lead_in) * SAMPLE_RATE)))

    params = None
    scene_samples: list[int] = []
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out_wav), "wb") as dst:
        for index, path in enumerate(scene_wavs):
            with wave.open(str(path), "rb") as src:
                if params is None:
                    params = (src.getnchannels(), src.getsampwidth(), src.getframerate())
                    if params[2] != SAMPLE_RATE:
                        raise TtsError(
                            f"معدل عينات غير متوقع: {params[2]} (المتوقع {SAMPLE_RATE})"
                        )
                    dst.setnchannels(params[0])
                    dst.setsampwidth(params[1])
                    dst.setframerate(params[2])
                frames = src.readframes(src.getnframes())
            scene_samples.append(len(frames) // (params[1] * params[0]))
            if index == 0 and lead_samples:
                # the lead-in belongs BEFORE the first word, not after the last
                dst.writeframes(b"\x00" * (params[1] * params[0] * lead_samples))
            dst.writeframes(frames)
            if index < gaps_count:
                silence = b"\x00" * (
                    params[1] * params[0] * int(round(pause_list[index] * params[2]))
                )
                dst.writeframes(silence)
    total = sum(scene_samples) + sum(
        int(round(p * SAMPLE_RATE)) for p in pause_list
    ) + lead_samples
    return {
        "path": str(out_wav),
        "total_samples": int(total),
        "duration_sec": round(total / SAMPLE_RATE, 6),
        "scene_samples": scene_samples,
        "pause_samples": [int(round(p * SAMPLE_RATE)) for p in pause_list],
        "lead_in_samples": lead_samples,
        "sample_rate": SAMPLE_RATE,
    }


# --------------------------------------------------------------------------
# الواجهة العليا
# --------------------------------------------------------------------------
def synthesize_narration(
    scenes: Sequence[str],
    out_wav: Path,
    cfg: TtsConfig,
    *,
    pauses: Sequence[float] | float = 0.8,
    lead_in: float = 0.35,
    work_dir: Path | None = None,
    synthesizer: Callable[[str, Path, TtsConfig], Path] | None = None,
) -> dict:
    """يولّد كل المشاهد ثم يجمّعها في ملف سرد واحد.

    ``synthesizer`` قابل للحقن — يسمح باختبار العقد بلا شبكة.
    """
    scenes = [str(s or "").strip() for s in scenes]
    if not scenes:
        raise TtsError("لا مشاهد لتوليدها")
    out_wav = Path(out_wav)
    work = Path(work_dir or (out_wav.parent / "_scenes"))
    work.mkdir(parents=True, exist_ok=True)
    synth = synthesizer or synthesize_scene
    scene_wavs: list[Path] = []
    for index, text in enumerate(scenes, 1):
        path = work / f"scene-{index:02d}.wav"
        synth(text, path, cfg, work_dir=work)
        if not path.exists() or path.stat().st_size == 0:
            raise TtsError(f"لم يُنتج المشهد {index} أي صوت")
        scene_wavs.append(path)
    report = assemble_narration(scene_wavs, out_wav, pauses=pauses, lead_in=lead_in)
    report["scenes"] = len(scenes)
    report["words"] = scene_words(scenes)
    report["backend"] = cfg.backend
    report["voice"] = cfg.resolved_voice()
    report["rate"] = cfg.rate
    report["pitch"] = cfg.pitch
    return report


def register_generated_narration(
    project_dir: str | Path,
    wav_path: str | Path,
    origin: dict,
    *,
    note: str = "",
) -> dict:
    """يستورد الملف المولَّد كسرد للمشروع مع تسجيل أصله."""
    return import_narration(project_dir, wav_path, copy=True, note=note, origin=origin)


def synthesize_project(
    project_dir: str | Path,
    scenes: Sequence[str],
    *,
    cfg: TtsConfig | None = None,
    pauses: Sequence[float] | float = 0.8,
    lead_in: float = 0.35,
    synthesizer: Callable[[str, Path, TtsConfig], Path] | None = None,
) -> dict:
    """يولّد سرد المشروع كاملًا ويسجّله داخله (استيراد + وصف)."""
    pd = Path(project_dir)
    cfg = cfg or TtsConfig.from_config(language="ar")
    tts_dir = pd / "audio" / "tts"
    tts_dir.mkdir(parents=True, exist_ok=True)
    out_wav = tts_dir / "narration-tts.wav"
    report = synthesize_narration(
        scenes,
        out_wav,
        cfg,
        pauses=pauses,
        lead_in=lead_in,
        work_dir=tts_dir / "_scenes",
        synthesizer=synthesizer,
    )
    origin = {
        "kind": "generated",
        "generated_by": "engine.tts",
        "backend": cfg.backend,
        "voice": report["voice"],
        "rate": cfg.rate,
        "pitch": cfg.pitch,
        "scenes": report["scenes"],
        "words": report["words"],
        "outside_project": False,
    }
    manifest = register_generated_narration(
        pd, out_wav, origin, note=f"generated by engine.tts ({cfg.backend})"
    )
    report["manifest"] = manifest
    report["stored"] = manifest.get("path")
    return report
