"""محاذاة السرد↔الصوت — بعقد صريح وبدرجة ثقة صادقة (لا ادعاء دقة زائفة).

مستويان هنا:

``APPROXIMATE`` (الأساسي)
    توزيع مدة الصوت على الجمل بنسب أطوال النصوص (حروف + وزن كلمات) بأعداد
    صحيحة دقيقة — بلا أي انزلاق وبلا تجاوز مدة الصوت.

``MEASURED`` / ``SEGMENTED`` (المرحلة الرابعة)
    بنية الوقف **مقيسة** من الصوت: نكشف المقاطع الناطقة (VAD energetic)، ثم
    نربط الجمل بها بالترتيب.  إن كان عدد المقاطع = عدد الجمل فالربط واحد-واحد
    وثقته عالية؛ وإلا فالتوزيع تناسبي على زمن النطق المقيس، وثقته أقل ويُقال
    سببها صراحةً.

المحاذاة الدقيقة كلمة-بكلمة تحتاج نموذج تفريغ صوتي؛ عند إضافته لاحقًا
يرتفع المستوى إلى ``WORD`` بنفس العقد دون تغيير المستهلكين.

كل الأرقام هنا وحدات عينات عند ``sample_rate`` المعلن في الوصف.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Sequence

import numpy as np

from ..core import arabic
from ..core.log import get_logger
from ..core.timebase import FrameRate, SampleRate, map_boundaries_to_frames
from ..core.util import write_json

log = get_logger("audio.align")

ALIGN_VERSION = 1
ALIGN_NAME = "alignment.json"

LEVEL_NONE = "NONE"
LEVEL_APPROX = "APPROXIMATE"
LEVEL_MEASURED = "MEASURED"
LEVEL_SEGMENTED = "SEGMENTED"
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


@dataclass
class SpeechSegment:
    """مقطع نطق مقيس (بحدود عينات)."""

    start_sample: int
    end_sample: int
    rms_dbfs: float

    @property
    def length(self) -> int:
        return self.end_sample - self.start_sample

    def to_dict(self) -> dict:
        return asdict(self)


def detect_speech(
    samples: np.ndarray,
    sample_rate: int,
    *,
    frame_ms: int = 20,
    min_speech_ms: int = 120,
    min_gap_ms: int = 180,
    noise_margin_db: float = 6.0,
    dynamic_range_db: float = 20.0,
) -> list[SpeechSegment]:
    """Detect the spoken segments of a signal (energy VAD).

    The threshold comes from the signal itself: the 10th percentile of the
    frame levels is the noise floor, the 95th percentile is the speech level,
    and the gate sits ``noise_margin_db`` above the floor (never more than
    ``dynamic_range_db`` below the speech level).  Nothing about the
    recording level is assumed.
    """
    x = np.asarray(samples, dtype=np.float64)
    if x.ndim == 2:
        x = x.mean(axis=0)
    if x.size == 0 or sample_rate <= 0:
        return []
    frame = max(1, int(round(frame_ms * sample_rate / 1000)))
    count = x.size // frame
    if count <= 0:
        return []
    frames = x[: count * frame].reshape(count, frame)
    rms = np.sqrt(np.mean(frames * frames, axis=1))
    with np.errstate(divide="ignore"):
        db = 20.0 * np.log10(np.where(rms > 0, rms, 1e-12))
    floor = float(np.percentile(db, 10))
    speech = float(np.percentile(db, 95))
    threshold = max(floor + noise_margin_db, speech - dynamic_range_db)

    voiced = db > threshold
    gap = max(1, int(round(min_gap_ms * sample_rate / 1000 / frame)))
    min_len = int(round(min_speech_ms * sample_rate / 1000))

    out: list[SpeechSegment] = []
    idx = 0
    while idx < voiced.size:
        if not voiced[idx]:
            idx += 1
            continue
        end = idx
        while True:
            look = end + 1
            while look < voiced.size and not voiced[look]:
                look += 1
            if look < voiced.size and (look - (end + 1)) <= gap:
                # a short pause inside the same utterance: close it and continue
                end = look
                continue
            break
        start_sample = idx * frame
        end_sample = min(int(x.size), (end + 1) * frame)
        if (end_sample - start_sample) >= min_len:
            out.append(
                SpeechSegment(
                    start_sample=start_sample,
                    end_sample=end_sample,
                    rms_dbfs=float(np.mean(db[idx : end + 1])),
                )
            )
        idx = end + 1
    return out


def _largest_remainder(total: int, weights: Sequence[int]) -> list[int]:
    """Split ``total`` into integer parts proportional to ``weights`` (exact sum)."""
    wsum = sum(weights)
    if wsum <= 0:
        return [0] * len(weights)
    raw = [Fraction(total * w, wsum) for w in weights]
    floors = [int(r) for r in raw]
    rest = total - sum(floors)
    order = sorted(range(len(weights)), key=lambda i: (raw[i] - floors[i], -i), reverse=True)
    for k in range(rest):
        floors[order[k % len(order)]] += 1
    return floors


def measured_align(
    scenes: Sequence[dict],
    samples: np.ndarray,
    sample_rate: int,
    total_samples: int,
) -> Alignment:
    """Align the scenes to the **measured** speech structure of the audio.

    * The pause structure is measured (energy VAD).
    * If the number of measured segments equals the number of scenes, the
      mapping is one to one (``MEASURED``, confidence 0.85).
    * Otherwise the scenes are spread over the measured speech time by text
      weight and the boundaries are snapped to the nearest measured pause
      (``SEGMENTED``, lower confidence, and the mismatch is stated).
    """
    if total_samples <= 0:
        raise AlignmentError(f"مدة الصوت غير صالحة: {total_samples} عينة")
    if sample_rate <= 0:
        raise AlignmentError(f"معدل العينات غير صالح: {sample_rate}")
    texts = [str(s.get("narration") or "").strip() for s in scenes]
    if not texts or any(not t for t in texts):
        raise AlignmentError("كل مشهد يجب أن يحمل نصًا غير فارغ للمحاذاة")
    ids = [int(s.get("id") or i + 1) for i, s in enumerate(scenes)]

    segments = detect_speech(samples, sample_rate)
    notes: list[str] = []
    if not segments:
        notes.append("لم يُكتشف أي مقطع نطق — تعذّرت المحاذاة المقيسة.")
        return Alignment(
            level=LEVEL_NONE,
            method="vad-energy-v1",
            sample_rate=sample_rate,
            total_samples=total_samples,
            segments=[],
            notes=notes,
        )

    notes.append(f"بنية الوقف مقيسة: {len(segments)} مقطع نطق مكتشف من الصوت فعليًا.")

    if len(segments) == len(scenes):
        level = LEVEL_MEASURED
        method = "vad-pauses-one-to-one-v1"
        conf = 0.85
        flags_common = ["pause-detected", "one-to-one"]
        # interior boundary i = the start of the next utterance: the pause
        # belongs to the scene that precedes it, so the ranges stay contiguous
        # and the last scene runs to the end of the audio.
        interior = [segments[i + 1].start_sample for i in range(len(segments) - 1)]
        notes.append("عدد المقاطع = عدد المشاهد ⇒ ربط واحد-واحد.")
    else:
        level = LEVEL_SEGMENTED
        method = "vad-pauses-proportional-v1"
        conf = 0.55
        flags_common = ["pause-detected", "proportional-mapping"]
        notes.append(
            f"عدد المقاطع المقيسة ({len(segments)}) ≠ عدد المشاهد ({len(scenes)}) ⇒ "
            "التوزيع تناسبي على زمن النطق المقيس، ثم يُحوَّل كل حد تراكمي إلى "
            "زمن التسجيل مع احتساب الوقفات التي تسبقه."
        )
        speech_total = sum(s.length for s in segments)
        weights = [_text_weight(t) for t in texts]
        parts = _largest_remainder(speech_total, weights)

        def speech_to_recording(offset: int) -> int:
            """Map a cumulative *spoken* sample offset to the recording clock.

            Walking the measured utterances is the whole point: if the first
            two scenes weigh half the speech, the boundary is at half of the
            **spoken** time, but its place in the recording must include every
            pause that came before it.  Snapping to a nearby pause edge (the
            old behaviour) silently discarded those pauses and started the
            scene too early.  At an exact end-of-utterance offset we return
            that end, so a boundary that falls on a pause stays on the pause.
            """
            cursor = 0
            for seg in segments:
                if offset <= cursor + seg.length:
                    return int(seg.start_sample + (offset - cursor))
                cursor += seg.length
            return int(total_samples)

        # Boundaries after each scene except the last; cumulative speech time
        # is converted to recording time rather than compressed into speech.
        interior: list[int] = []
        cumulative = 0
        for i in range(len(scenes) - 1):
            cumulative += parts[i]
            boundary = speech_to_recording(cumulative)
            # Integer rounding must never create a zero-length scene; leave at
            # least one sample for every remaining scene.
            remaining = len(scenes) - 1 - i
            upper = max(0, int(total_samples) - remaining)
            boundary = min(boundary, upper)
            if interior:
                boundary = max(boundary, interior[-1] + 1)
            else:
                boundary = max(1, boundary)
            interior.append(int(boundary))

    # the picture covers the whole recording: [0 .. total_samples]
    bounds = [0] + [int(b) for b in interior] + [int(total_samples)]
    for i in range(1, len(bounds)):
        if bounds[i] <= bounds[i - 1]:
            bounds[i] = bounds[i - 1] + 1
    if bounds[-1] <= bounds[-2]:
        bounds[-1] = bounds[-2] + 1
    bounds[-1] = max(bounds[-1], bounds[-2])
    if bounds[-1] > total_samples:
        bounds[-1] = int(total_samples)

    segs: list[Segment] = []
    for i, t in enumerate(texts):
        start, end = int(bounds[i]), int(bounds[i + 1])
        flags = list(flags_common)
        if end <= start:
            conf_i = 0.2
            flags.append("zero-length")
        else:
            conf_i = conf
        segs.append(
            Segment(
                scene_id=ids[i],
                text=t,
                start_sample=start,
                end_sample=end,
                confidence=conf_i,
                flags=flags,
            )
        )

    notes.append("التوقيت مرجعه عدد عينات الصوت الفعلي (بلا انزلاق).")
    return Alignment(
        level=level,
        method=method,
        sample_rate=sample_rate,
        total_samples=total_samples,
        segments=segs,
        notes=notes,
    )


# --------------------------------------------------------------------------
# المستوىWORD — توقيت الكلمة من تفريغ صوتي مقيس
# --------------------------------------------------------------------------
@dataclass
class WordTiming:
    """كلمة بتوقيتها المقيس (ثوانٍ) واحتمالها من النموذج."""

    text: str
    start_sec: float
    end_sec: float
    prob: float = 0.0


def _tokens(text: str) -> list[str]:
    """تطبيع النص إلى رموز قابلة للمطابقة (بلا تشكيل ولا وقفيات)."""
    out: list[str] = []
    for word in arabic.words(text or ""):
        token = arabic.normalize(word).lower().strip()
        if token:
            out.append(token)
    return out


def word_align(
    scenes: Sequence[dict],
    words: Sequence[WordTiming],
    *,
    sample_rate: int,
    total_samples: int,
    min_match_ratio: float = 0.45,
) -> Alignment:
    """يوزّع المشاهد على **كلمات مفرغة من الصوت نفسه** (المستوى ``WORD``).

    الفكرة: التفريغ يعطي لكل كلمة زمنها المقيس. نطابق رموز المشاهد (نص
    السرد) مع رموز التفريغ تسلسليًّا، ثم نبني حدود المشاهد من الكلمات
    المتطابقة فعلًا. المشهد الذي لا تُطابق كلماته يُعلَّم صراحةً
    (``unmatched``) ولا يُدّعى أنه مضبوط.

    المخرجات **متّصلة** كما يفرض عقد الإنتاج: تبدأ من العيّنة صفر وتنتهي عند
    نهاية الصوت، بلا فجوة ولا تداخل.
    """
    import difflib

    if total_samples <= 0:
        raise AlignmentError(f"مدة الصوت غير صالحة: {total_samples} عينة")
    if sample_rate <= 0:
        raise AlignmentError(f"معدل العينات غير صالح: {sample_rate}")
    texts = [str(s.get("narration") or "").strip() for s in scenes]
    if not texts or any(not t for t in texts):
        raise AlignmentError("كل مشهد يجب أن يحمل نصًا غير فارغ للمحاذاة")
    ids = [int(s.get("id") or i + 1) for i, s in enumerate(scenes)]

    notes: list[str] = []
    if not words:
        notes.append("لا كلمات مفرغة — تعذّرت المحاذاة على مستوى الكلمة.")
        return Alignment(
            level=LEVEL_NONE,
            method="asr-word-timed-v1",
            sample_rate=sample_rate,
            total_samples=total_samples,
            segments=[],
            notes=notes,
        )

    # --- 1) مطابقة الرموز تسلسليًّا -------------------------------------
    scene_tokens: list[str] = []
    token_scene: list[int] = []
    scene_token_counts: list[int] = []
    for index, text in enumerate(texts):
        toks = _tokens(text)
        scene_token_counts.append(len(toks))
        for token in toks:
            scene_tokens.append(token)
            token_scene.append(index)

    asr_tokens: list[str] = []
    asr_times: list[tuple[float, float, float]] = []
    for word in words:
        token = _tokens(word.text)
        if not token:
            continue
        asr_tokens.append(token[0])
        asr_times.append((float(word.start_sec), float(word.end_sec), float(word.prob or 0.0)))

    matched: dict[int, list[int]] = {}
    if scene_tokens and asr_tokens:
        matcher = difflib.SequenceMatcher(None, scene_tokens, asr_tokens, autojunk=False)
        for a, b, size in matcher.get_matching_blocks():
            for offset in range(size):
                scene_index = token_scene[a + offset]
                matched.setdefault(scene_index, []).append(b + offset)

    # --- 2) مدى كل مشهد من كلماته المطابقة ------------------------------
    span_start: list[float | None] = []
    span_end: list[float | None] = []
    span_probs: list[list[float]] = []
    for index in range(len(scenes)):
        hits = matched.get(index, [])
        if hits:
            span_start.append(asr_times[hits[0]][0])
            span_end.append(asr_times[hits[-1]][1])
            span_probs.append([asr_times[h][2] for h in hits])
        else:
            span_start.append(None)
            span_end.append(None)
            span_probs.append([])

    # --- 3) الحدود بين المشاهد ------------------------------------------
    count = len(scenes)
    interior: list[float] = []
    known: dict[int, float] = {}
    for index in range(count - 1):
        left = span_end[index]
        right = span_start[index + 1]
        if left is not None and right is not None:
            value = (left + right) / 2.0
            if right < left:
                # ترتيب معكوس (خطأ في المطابقة): نأخذ الحدّ الأبعد عن البداية
                value = max(left, right)
        elif left is not None:
            value = left
        elif right is not None:
            value = right
        else:
            value = None
        if value is not None:
            known[index] = value
        interior.append(value if value is not None else 0.0)

    # الحدود المجهولة تُشتق خطيًا من أقرب حدّ معروف (لا تخمين صامت)
    for index in range(count - 1):
        if index in known:
            continue
        prev = next((i for i in range(index - 1, -1, -1) if i in known), None)
        nxt = next((i for i in range(index + 1, count - 1) if i in known), None)
        if prev is not None and nxt is not None:
            span = nxt - prev
            ratio = (index - prev) / span if span else 0.0
            interior[index] = known[prev] + (known[nxt] - known[prev]) * ratio
        elif prev is not None:
            interior[index] = known[prev]
        elif nxt is not None:
            interior[index] = known[nxt]

    # --- 4) تحويل إلى عيّنات + رتابة صارمة + تغطية كاملة -----------------
    total_sec = total_samples / float(sample_rate)
    bounds: list[float] = [0.0]
    for value in interior:
        bounds.append(max(0.0, min(total_sec, float(value))))
    bounds.append(float(total_sec))

    # الحدود بالعيّنات: **صارمة التزايد** (كل مشهد له عيّنة واحدة على الأقل)
    # حتى يمرّ فحص «التغطية المتصلة» في عقد الإنتاج بلا رفض.
    sample_bounds: list[int] = [0]
    for value in bounds[1:]:
        sample_bounds.append(int(round(value * sample_rate)))
    sample_bounds[-1] = int(total_samples)
    for i in range(1, len(sample_bounds)):
        if sample_bounds[i] <= sample_bounds[i - 1]:
            sample_bounds[i] = sample_bounds[i - 1] + 1
    overflow = sample_bounds[-1] - int(total_samples)
    if overflow > 0:
        # نضغط من النهاية مع الحفاظ على التزايد الصارم
        for i in range(len(sample_bounds) - 1, 0, -1):
            sample_bounds[i] = min(sample_bounds[i], int(total_samples) - (len(sample_bounds) - 1 - i))
            if sample_bounds[i] > sample_bounds[i - 1]:
                break
        sample_bounds[0] = 0
        sample_bounds[-1] = int(total_samples)
        for i in range(1, len(sample_bounds)):
            if sample_bounds[i] <= sample_bounds[i - 1]:
                sample_bounds[i] = sample_bounds[i - 1]

    segs: list[Segment] = []
    matched_scenes = 0
    total_scene_tokens = 0
    matched_tokens = 0
    for index, text in enumerate(texts):
        start = sample_bounds[index]
        end = sample_bounds[index + 1]
        hits = matched.get(index, [])
        count_tokens = scene_token_counts[index]
        ratio = (len(hits) / count_tokens) if count_tokens else 0.0
        total_scene_tokens += count_tokens
        matched_tokens += len(hits)
        flags: list[str] = []
        if hits:
            matched_scenes += 1
            flags.append("asr-word-timed")
            confidence = 0.75 if ratio >= min_match_ratio else 0.6
            if ratio < min_match_ratio:
                flags.append("partial-match")
        else:
            confidence = 0.3
            flags.append("unmatched")
        probs = span_probs[index]
        if probs:
            mean_prob = sum(probs) / len(probs)
            if mean_prob < 0.5:
                confidence = min(confidence, 0.55)
                flags.append("low-confidence")
        if end <= start:
            confidence = min(confidence, 0.2)
            flags.append("zero-length")
        segs.append(
            Segment(
                scene_id=ids[index],
                text=text,
                start_sample=start,
                end_sample=end,
                confidence=round(confidence, 3),
                flags=flags,
            )
        )

    coverage = (matched_tokens / total_scene_tokens) if total_scene_tokens else 0.0
    notes.append(
        f"توقيت الكلمة من تفريغ صوتي مقيس: {len(asr_tokens)} كلمة مفرغة · "
        f"{matched_scenes}/{count} مشهد طابق بالكلمات · تغطية الرموز {coverage:.0%}."
    )
    if matched_scenes < count:
        notes.append(
            "⚠ مشاهد بلا مطابقة كلامية — حدودها **مقدّرة** من جيرانها (لا تُدّعى دقتها)."
        )
    notes.append("التوقيت مرجعه عدد عينات الصوت الفعلي (بلا انزلاق).")
    return Alignment(
        level=LEVEL_WORD,
        method="asr-word-timed-v1",
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
