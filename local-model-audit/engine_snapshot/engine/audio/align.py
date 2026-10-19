"""محاذاة السرد↔الصوت — بعقد صريح وبدرجة ثقة صادقة (لا ادعاء دقة زائفة).

المستوى الأساسي هنا ``APPROXIMATE``: توزيع مدة الصوت على الجمل بنسب أطوال
النصوص (حروف + وزن كلمات) بأعداد صحيحة دقيقة — بلا أي انزلاق وبلا تجاوز مدة
الصوت. المحاذاة الدقيقة كلمة-بكلمة تحتاج نموذج تفريغ صوتي؛ عند إضافته لاحقًا
يرتفع المستوى إلى ``WORD`` بنفس العقد دون تغيير المستهلكين.

كل الأرقام هنا وحدات عينات عند ``sample_rate`` المعلن في الوصف.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Sequence

from ..core import arabic
from ..core.log import get_logger
from ..core.timebase import FrameRate, SampleRate, map_boundaries_to_frames
from ..core.util import write_json

log = get_logger("audio.align")

ALIGN_VERSION = 1
ALIGN_NAME = "alignment.json"

LEVEL_NONE = "NONE"
LEVEL_APPROX = "APPROXIMATE"
LEVEL_WORD = "WORD"


class AlignmentError(ValueError):
    """عقد محاذاة غير صالح."""


@dataclass
class Segment:
    scene_id: int
    text: str
    start_sample: int
    end_sample: int
    confidence: float
    flags: list[str] = field(default_factory=list)

    @property
    def length(self) -> int:
        return self.end_sample - self.start_sample


@dataclass
class Alignment:
    level: str
    method: str
    sample_rate: int
    total_samples: int
    segments: list[Segment]
    notes: list[str] = field(default_factory=list)
    version: int = ALIGN_VERSION

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "level": self.level,
            "method": self.method,
            "sample_rate": self.sample_rate,
            "total_samples": self.total_samples,
            "notes": list(self.notes),
            "segments": [asdict(s) for s in self.segments],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Alignment":
        return cls(
            level=d.get("level", LEVEL_NONE),
            method=d.get("method", ""),
            sample_rate=int(d.get("sample_rate") or 0),
            total_samples=int(d.get("total_samples") or 0),
            segments=[Segment(**s) for s in d.get("segments", [])],
            notes=list(d.get("notes", [])),
            version=int(d.get("version") or 1),
        )


def _text_weight(text: str) -> int:
    """وزن الجملة = حروف بلا مسافات + 6 لكل كلمة (كلمة أقصر ≈ زمن أكبر نسبةً)."""
    t = (text or "").strip()
    letters = sum(1 for ch in arabic.normalize(t) if not ch.isspace())
    words = len(t.split())
    return max(1, letters + 6 * words)


def baseline_align(
    scenes: Sequence[dict],
    total_samples: int,
    sample_rate: int,
    *,
    min_conf: float = 0.5,
    speech_rate_check: bool = True,
) -> Alignment:
    """توزيع تقديري صريح لمدة الصوت على المشاهد — أعداد صحيحة بلا انزلاق.

    - يرفض ``total_samples`` غير موجب أو مشاهد بلا نص.
    - الحدود تُحسب بطريقة الباقي الأكبر (largest remainder) فالمجموع = المدة تمامًا.
    - الجمل ذات معدل الكلام المستحيل (حروف/ثانية متطرفة مقارنة بالوسيط > 60%)
      تُعلَّم ``rate-extreme`` وتُخفَّض ثقتها — بدل الادعاء أنها دقيقة.
    """
    if total_samples <= 0:
        raise AlignmentError(f"مدة الصوت غير صالحة: {total_samples} عينة")
    if sample_rate <= 0:
        raise AlignmentError(f"معدل العينات غير صالح: {sample_rate}")
    texts = [str(s.get("narration") or "").strip() for s in scenes]
    if not texts or any(not t for t in texts):
        raise AlignmentError("كل مشهد يجب أن يحمل نصًا غير فارغ للمحاذاة")
    ids = [int(s.get("id") or i + 1) for i, s in enumerate(scenes)]

    weights = [_text_weight(t) for t in texts]
    wsum = sum(weights)

    # حدود دقيقة: cum_i = round(total * W_i / W)
    bounds = [0]
    cum = 0
    for w in weights:
        cum += w
        b = Fraction(total_samples * cum, wsum)
        bounds.append((b + Fraction(1, 2)).numerator // (b + Fraction(1, 2)).denominator)
    bounds[0] = 0
    bounds[-1] = total_samples
    for i in range(1, len(bounds)):
        if bounds[i] < bounds[i - 1]:
            bounds[i] = bounds[i - 1]

    # فحص معدل الكلام: حروف/ثانية ضمن نطاق معقول
    median_rate = None
    if speech_rate_check and total_samples > 0:
        rates = sorted(
            (len(texts[i].replace(" ", "")) / max(1e-6, (bounds[i + 1] - bounds[i]) / sample_rate))
            for i in range(len(texts))
        )
        median_rate = rates[len(rates) // 2] if rates else None

    segs: list[Segment] = []
    implausible = bool(median_rate and (median_rate < 5.0 or median_rate > 28.0))
    for i, t in enumerate(texts):
        start, end = bounds[i], bounds[i + 1]
        conf = 0.35
        flags: list[str] = ["proportional-characters"]
        if median_rate:
            dur_s = max(1e-6, (end - start) / sample_rate)
            rate = len(t.replace(" ", "")) / dur_s
            if median_rate > 0 and (rate > median_rate * 1.6 or rate < median_rate / 1.6):
                conf = 0.2
                flags.append("rate-extreme")
        if implausible:
            conf = 0.15
            flags.append("rate-implausible")
        if end <= start:
            conf = 0.1
            flags.append("zero-length")
        segs.append(Segment(scene_id=ids[i], text=t, start_sample=start, end_sample=end, confidence=conf, flags=flags))

    notes = [
        "محاذاة تقديرية بنِسَب أطوال النصوص — ليست محاذاة صوتية دقيقة.",
        "التوقيت مرجعه عدد عينات الصوت الفعلي (بلا انزلاق)، لكن توزيعه تقديري.",
    ]
    if median_rate:
        notes.append(f"وسيط معدل الكلام المقدر ≈ {median_rate:.2f} حرف/ثانية.")
    if implausible:
        notes.append(
            f"⚠ معدل الكلام المقدر غير معقول ({median_rate:.2f} حرف/ث): النص والصوت غير متطابقين على الأرجح — "
            "راجع مدة التسجيل/طول السكريبت قبل الاعتماد على التوقيت."
        )
    return Alignment(
        level=LEVEL_APPROX,
        method="proportional-characters-v1",
        sample_rate=sample_rate,
        total_samples=total_samples,
        segments=segs,
        notes=notes,
    )


def save_alignment(al: Alignment, project_dir: str | Path) -> Path:
    d = Path(project_dir) / "audio"
    d.mkdir(parents=True, exist_ok=True)
    return write_json(d / ALIGN_NAME, al.to_dict())


def load_alignment(project_dir: str | Path) -> Alignment | None:
    import json

    p = Path(project_dir) / "audio" / ALIGN_NAME
    if not p.exists():
        return None
    try:
        return Alignment.from_dict(json.loads(p.read_text(encoding="utf-8")))
    except Exception as e:  # عقد قديم/تالف → نرفض بدل الادعاء
        log.warning("محاذاة غير مقروءة (%s) — تُتجاهل", e)
        return None


def alignment_frames(al: Alignment, *, fps: FrameRate) -> list[dict]:
    """يحوّل المقاطع إلى نطاقات إطارات نصف-مفتوحة [start, end) — تعيين مطلق دقيق."""
    sr = SampleRate(al.sample_rate)
    bounds = [s.start_sample for s in al.segments] + ([al.segments[-1].end_sample] if al.segments else [])
    frames = map_boundaries_to_frames(bounds, sr, fps, total_samples=al.total_samples)
    out: list[dict] = []
    for i, s in enumerate(al.segments):
        fs, fe = frames[i], frames[i + 1]
        out.append(
            {
                "scene_id": s.scene_id,
                "start_frame": fs,
                "end_frame": max(fe, fs),
                "start_sec": float(Fraction(fs * fps.den, fps.num)),
                "end_sec": float(Fraction(fe * fps.den, fps.num)),
                "confidence": s.confidence,
                "flags": list(s.flags),
            }
        )
    return out
