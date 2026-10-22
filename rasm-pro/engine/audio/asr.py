"""تفريغ صوتي محلي — يحوّل تسجيل السرد إلى **توقيت لكل كلمة**.

لماذا هذا الملف موجود
----------------------
كان مستوى المحاذاة ``SEGMENTED`` (0.55): بنية الوقف مقيسة، لكن توزيع الجمل على
الزمن **تقديري**. لا وجود لتوقيت كلمة، فلا شفاه ولا إبراز. المستوى ``WORD`` كان
معلَنًا في العقد بلا تنفيذ.

هذا الملف ينفّذ الطرف الذي كان ناقصًا: تفريغ الصوت **محليًّا** (بلا سحابة وبلا
اشتراك) عبر ``whisper.cpp``، ويعطي لكل كلمة زمن بداية ونهاية **مقيسة** من
التسجيل نفسه.

الأدوات (كلها محلية، وكلها اختيارية):
* ``runtime/whisper/Release/whisper-cli.exe`` — تنفيذ whisper.cpp
* ``runtime/whisper/models/ggml-*.bin`` — النموذج (tiny = 75MB متعدّد اللغات)

القواعد (كما في بقية المحرك):
* لا انزلاق صامت: إن لم توجد الأداة ⇒ خطأ صريح يشرح ما ينقص.
* الصوت يُعاد تشكيله إلى 16kHz أحادي قبل التفريغ — القياس على الأصل لا يُلمس.
* الثقة تُقاس: كل كلمة تحمل احتمالها من النموذج، والمشاهد غير المطابقة تُعلَّم.
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Sequence

from ..core.log import get_logger

log = get_logger("audio.asr")

ASR_BACKENDS = ("none", "whisper-cpp")
ASR_NAME = "transcript.json"

# نماذج whisper.cpp المفضلة بالترتيب (الأصغر أولًا: أسرع وأخف على الجهاز).
_MODEL_PREFERENCE = (
    "ggml-tiny.bin",
    "ggml-base.bin",
    "ggml-small.bin",
    "ggml-medium.bin",
)

# رموز خاصة في مخرجات whisper.cpp — ليست كلمات.
_SPECIAL_PREFIXES = ("[_BEG_", "[_TT_", "[_BOD_", "<|", "[_EOT_", "[_SOT_", "[_TRANSLATE_", "[_NOT_", "[_NO_", "[_PAD_", "[_PREV_", "[_NEXT_", "[_MASK_", "[_SOL_", "[_NL_", "[_SO_", "[_EL_", "[_EOT_]")


class AsrError(RuntimeError):
    """تعذّر التفريغ — يُرفع كخطأ صريح (لا ملف صامت)."""


@dataclass
class Word:
    """كلمة واحدة بتوقيتها المقيس (بالثواني) واحتمالها."""

    text: str
    start_sec: float
    end_sec: float
    prob: float = 0.0

    @property
    def duration(self) -> float:
        return max(0.0, self.end_sec - self.start_sec)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Transcript:
    backend: str
    language: str
    model: str
    words: list[Word] = field(default_factory=list)
    segments: int = 0
    duration_sec: float = 0.0
    seconds_wall: float = 0.0
    audio_sha256: str = ""
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "backend": self.backend,
            "language": self.language,
            "model": self.model,
            "segments": self.segments,
            "duration_sec": round(self.duration_sec, 6),
            "seconds_wall": round(self.seconds_wall, 3),
            "audio_sha256": self.audio_sha256,
            "words": [w.to_dict() for w in self.words],
            "notes": list(self.notes),
        }


# --------------------------------------------------------------------------
# اكتشاف الأدوات (محلية فقط — لا تنزيل تلقائي)
# --------------------------------------------------------------------------
def runtime_root() -> Path:
    """جذر الأدوات المحلية: ``<repo>/rasm-pro/runtime``."""
    return Path(__file__).resolve().parents[2] / "runtime"


def discover_binary(root: Path | None = None) -> Path | None:
    """يبحث عن ``whisper-cli.exe`` (أو ``main.exe``) في مجلد الأدوات المحلي."""
    base = Path(root) if root else runtime_root()
    candidates = [
        base / "whisper" / "Release" / "whisper-cli.exe",
        base / "whisper" / "Release" / "main.exe",
        base / "whisper" / "whisper-cli.exe",
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def discover_model(root: Path | None = None) -> Path | None:
    """يبحث عن نموذج ggml محلي (الأصغر أولًا)."""
    base = Path(root) if root else runtime_root()
    models_dir = base / "whisper" / "models"
    for name in _MODEL_PREFERENCE:
        path = models_dir / name
        if path.exists():
            return path
    if models_dir.exists():
        found = sorted(models_dir.glob("ggml-*.bin"))
        if found:
            return found[0]
    return None


def asr_status(root: Path | None = None) -> dict:
    """تقرير جاهزية الأداة (للفحص والواجهة)."""
    binary = discover_binary(root)
    model = discover_model(root)
    return {
        "backend": "whisper-cpp" if binary and model else "none",
        "binary": str(binary) if binary else None,
        "model": str(model) if model else None,
        "model_bytes": model.stat().st_size if model else 0,
        "available": bool(binary and model),
    }


# --------------------------------------------------------------------------
# التنفيذ
# --------------------------------------------------------------------------
def _ffmpeg() -> str:
    from ..render.video import require_ffmpeg

    return require_ffmpeg()


def to_16k_wav(src: str | Path, dst: str | Path) -> Path:
    """يعيد تشكيل الصوت إلى WAV PCM16 أحادي 16kHz (ما يقبله whisper.cpp).

    الأصل **لا يُلمس**: الملف الجديد نسخة منفصلة.
    """
    src = Path(src)
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        _ffmpeg(), "-y", "-v", "error", "-i", str(src),
        "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(dst),
    ]
    proc = subprocess.run(cmd, capture_output=True, timeout=300)
    if proc.returncode != 0:
        raise AsrError(
            "فشل إعادة تشكيل الصوت إلى 16kHz: "
            + proc.stderr.decode("utf-8", "replace")[-300:]
        )
    if not dst.exists() or dst.stat().st_size <= 44:
        raise AsrError("الملف المعاد تشكيله فارغ — لا تفريغ عليه.")
    return dst


def _is_special(token: str) -> bool:
    text = token.strip()
    if not text:
        return True
    return any(text.startswith(prefix) for prefix in _SPECIAL_PREFIXES)


def parse_whisper_tokens(payload: dict) -> tuple[list[Word], int]:
    """يحوّل مخرجات ``whisper-cli -ojf`` إلى كلمات بتوقيتات.

    whisper.cpp يعطي **رموزًا** (tokens) لا كلمات؛ الكلمة = مجموعة رموز تبدأ
    بمسافة (أو فاصل). كل رمز يحمل ``offsets`` بالملي ثانية.
    """
    words: list[Word] = []
    segments = 0
    current: Word | None = None
    current_probs: list[float] = []

    for segment in payload.get("transcription") or []:
        segments += 1
        tokens = segment.get("tokens")
        if tokens is None:
            # مخرجات ``-oj`` (بلا رموز): نستخدم النص segماعيًا بلا توقيت لكل كلمة
            text = str(segment.get("text") or "").strip()
            offsets = segment.get("offsets") or {}
            if text:
                start = float(offsets.get("from") or 0) / 1000.0
                end = float(offsets.get("to") or 0) / 1000.0
                for piece in text.split():
                    words.append(Word(text=piece, start_sec=start, end_sec=end, prob=0.0))
            continue
        for token in tokens:
            text = str(token.get("text") or "")
            if _is_special(text):
                continue
            offsets = token.get("offsets") or {}
            start = float(offsets.get("from") or 0) / 1000.0
            end = float(offsets.get("to") or 0) / 1000.0
            prob = float(token.get("p") or 0.0)
            starts_word = text[:1].isspace()
            if starts_word:
                if current is not None:
                    current.prob = (sum(current_probs) / len(current_probs)) if current_probs else 0.0
                    words.append(current)
                    current = None
                    current_probs = []
                current = Word(text=text.strip(), start_sec=start, end_sec=end)
                current_probs = [prob]
            else:
                if current is None:
                    current = Word(text=text.strip(), start_sec=start, end_sec=end)
                    current_probs = [prob]
                else:
                    current.text += text
                    current.end_sec = max(current.end_sec, end)
                    current_probs.append(prob)
    if current is not None:
        current.prob = (sum(current_probs) / len(current_probs)) if current_probs else 0.0
        words.append(current)

    # الكلمة الفارغة تُهمل، والزمن لا ينزل تحت الصفر
    words = [w for w in words if w.text.strip()]
    for word in words:
        word.end_sec = max(word.start_sec, word.end_sec)
    return words, segments


def transcribe(
    audio_file: str | Path,
    *,
    backend: str = "whisper-cpp",
    language: str = "ar",
    model: str | Path | None = None,
    binary: str | Path | None = None,
    threads: int = 4,
    work_dir: str | Path | None = None,
    timeout_s: int = 900,
    audio_sha256: str = "",
) -> Transcript:
    """يفرّغ ملفًا صوتيًا محليًّا إلى كلمات بتوقيتات مقيسة."""
    backend = str(backend or "none").strip().lower()
    if backend == "none":
        raise AsrError(
            "لا مزوّد تفريغ مفعَّل. المتاح: whisper-cpp (محلي) — "
            "ضع التنفيذ والنموذج في runtime/whisper."
        )
    if backend not in ASR_BACKENDS:
        raise AsrError(f"مزوّد تفريغ غير معروف: {backend!r} — المتاح: {', '.join(ASR_BACKENDS)}")

    src = Path(audio_file)
    if not src.exists():
        raise AsrError(f"ملف الصوت غير موجود: {src}")

    exe = Path(binary) if binary else discover_binary()
    if not exe or not Path(exe).exists():
        raise AsrError(
            "لم يُعثر على whisper-cli محلي. ضع التنفيذ في "
            "runtime/whisper/Release/whisper-cli.exe (أو مرّر --binary)."
        )
    model_path = Path(model) if model else discover_model()
    if not model_path or not Path(model_path).exists():
        raise AsrError(
            "لم يُعثر على نموذج ggml محلي. ضع النموذج في runtime/whisper/models "
            "(مثل ggml-tiny.bin) أو مرّر --model."
        )

    work = Path(work_dir) if work_dir else src.parent / "_asr"
    work.mkdir(parents=True, exist_ok=True)
    wav16 = to_16k_wav(src, work / (src.stem + ".16k.wav"))
    prefix = work / "transcript"

    cmd = [
        str(exe),
        "-m", str(model_path),
        "-f", str(wav16),
        "-l", str(language or "auto"),
        "-t", str(max(1, int(threads))),
        "-ojf",
        "-of", str(prefix),
        "-np",
    ]
    started = subprocess.run(cmd, capture_output=True, timeout=timeout_s)
    json_path = prefix.with_suffix(".json")
    if not json_path.exists():
        detail = (started.stderr or b"").decode("utf-8", "replace")[-300:]
        detail = detail or (started.stdout or b"").decode("utf-8", "replace")[-300:]
        raise AsrError(f"لم يُنتج whisper.cpp أي تفريغ (رمز {started.returncode}): {detail}")
    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise AsrError(f"مخرجات التفريغ غير مقروءة: {exc}") from exc

    words, segments = parse_whisper_tokens(payload)
    duration = max((w.end_sec for w in words), default=0.0)
    notes: list[str] = []
    if not words:
        notes.append("لم تُستخرج أي كلمة — قد يكون الصوت صامتًا أو النموذج ضعيفًا لهذه اللغة.")
    transcript = Transcript(
        backend=backend,
        language=str(language or "auto"),
        model=str(model_path),
        words=words,
        segments=segments,
        duration_sec=duration,
        audio_sha256=str(audio_sha256 or ""),
        notes=notes,
    )
    return transcript


def save_transcript(transcript: Transcript, project_dir: str | Path) -> Path:
    """يكتب التفريغ داخل المشروع (``audio/transcript.json``)."""
    from ..core.util import write_json

    d = Path(project_dir) / "audio"
    d.mkdir(parents=True, exist_ok=True)
    return write_json(d / ASR_NAME, transcript.to_dict())


def load_transcript(project_dir: str | Path) -> dict | None:
    """يقرأ التفريغ المحفوظ (إن وُجد)."""
    p = Path(project_dir) / "audio" / ASR_NAME
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # عقد تالف → نرفض بدل الادعاء
        log.warning("تفريغ غير مقروء (%s) — يُتجاهل", exc)
        return None


def transcript_words(payload: dict | None) -> list[Word]:
    """يستخرج الكلمات من تفريغ محفوظ."""
    if not payload:
        return []
    out: list[Word] = []
    for item in payload.get("words") or []:
        try:
            out.append(
                Word(
                    text=str(item.get("text") or ""),
                    start_sec=float(item.get("start_sec") or 0.0),
                    end_sec=float(item.get("end_sec") or 0.0),
                    prob=float(item.get("prob") or 0.0),
                )
            )
        except (TypeError, ValueError):
            continue
    return out


__all__ = [
    "ASR_BACKENDS",
    "ASR_NAME",
    "AsrError",
    "Transcript",
    "Word",
    "asr_status",
    "discover_binary",
    "discover_model",
    "load_transcript",
    "parse_whisper_tokens",
    "save_transcript",
    "to_16k_wav",
    "transcribe",
    "transcript_words",
]
