"""مؤثرات صوتية حقيقية (ملكية عامة) — مكتبة بأنواع مقيَّسة وأدوار دلالية.

المرحلة الخامسة — القواعد:
1. **كل تسجيل له دور واحد محدد.** ما لا يخدم دورًا لا يُحتفظ به.
2. **كل مستوى مقيس.** لا أرقام يدوية: مستوى كل مقطع يُقاس ويُعاد إلى هدف
   المكتبة، فتصبح «الأنواع» قابلة للمقارنة والمزج.
3. **لا تدهور صامت.** إن غاب التسجيل الحقيقي يُقال ذلك في التقرير ويُمنع
   الإنتاج — ولا يُستبدل بصوت توليدي في صمت.
4. **الربط دلالي:** نوع العنصر في الفيديو يحدد نوع الصوت (كتابة يدوية ↔
   خدش قلم، بطاقة ↔ ورق، نقطة ↔ نقرة).

المكتبة:

| النوع | التسجيل | الدور | الاشتقاق |
|---|---|---|---|
| `scratch` | pen_ink | خط الكتابة اليدوية | مباشر |
| `scratch_soft` | pen_felt | الخطوط الخفيفة (تظليل/تسطير) | مباشر |
| `scratch_fast` | pen_ink | العلامات السريعة (زخرفة/سهم) | تشغيل أسرع (varispeed) |
| `tick` | pen_ink | نقطة/ضغطة القلم | مقطع قصير |
| `page` | page_turn | نقل بطاقة/انتقال مشهد | مباشر |
| `page_soft` | page_turn | وضع صورة/خلفية | أبطأ وأخف |

الأرقام في `assets/sfx/calibration.json` كلها مقيسة بـ`tools/measure_sfx.py`.
"""
from __future__ import annotations

import json
import math
import random
import struct
import wave
from pathlib import Path

import numpy as np

from ..core.log import get_logger

log = get_logger("sfx")

SR = 48000
SFX_DIR = Path(__file__).resolve().parents[2] / "assets" / "sfx"
CALIBRATION_FILE = SFX_DIR / "calibration.json"

# مستوى المكتبة المرجعي: كل مقطع يُعاد إليه بالقياس (لا بأرقام يدوية).
LIBRARY_TARGET_RMS_DBFS = -30.0
# سقف الذروة لكل مقطع قبل المزج (حماية من التشويه).
EVENT_PEAK_CEILING = 0.7
# سقف ذروة المسار بعد التجميع.
TRACK_PEAK_CEILING = 0.89

# الإزاحة (dB) لكل نمط فوق مرجع المكتبة: "أقوى/أخف" صريح ومقروء.
PRESETS = {
    "paper":  {"offset_db": 0.0,  "sfx_mix_db": -9.1},   # 0.35 خطي مقابل سرد 1.0
    "subtle": {"offset_db": -6.0, "sfx_mix_db": -13.1},
    "bold":   {"offset_db": 3.0,  "sfx_mix_db": -6.1},
}

# الأنواع: التسجيل المصدر + الاشتقاق + الدور.
SFX_TYPES: dict[str, dict] = {
    "scratch": {
        "source": "pen_ink.wav",
        "role": "handwriting",
        "rate": 1.0,
        "kind": "stroke",
        "description": "خط الكتابة اليدوية — الطبقة الأساسية لكل حركة رسم",
    },
    "scratch_soft": {
        "source": "pen_felt.wav",
        "role": "light stroke",
        "rate": 1.0,
        "kind": "stroke",
        "description": "الخطوط الخفيفة (تظليل/تسطير) — نسيج ألطف",
    },
    "scratch_fast": {
        "source": "pen_ink.wav",
        "role": "quick mark",
        "rate": 1.45,
        "kind": "stroke",
        "description": "العلامات السريعة (زخرفة/سهم/خط زمني) — أسرع وأقصر",
    },
    "tick": {
        "source": "pen_ink.wav",
        "role": "point / tap",
        "rate": 1.0,
        "kind": "tap",
        "description": "نقطة الإعجام — نقرة قصيرة",
    },
    "page": {
        "source": "page_turn.wav",
        "role": "card / scene transition",
        "rate": 1.0,
        "kind": "paper",
        "description": "نقل بطاقة أو انتقال مشهد — صوت ورق حقيقي",
    },
    "page_soft": {
        "source": "page_turn.wav",
        "role": "soft placement",
        "rate": 0.85,
        "kind": "paper",
        "description": "وضع صورة أو خلفية — ورق أخف",
    },
}

# الربط الدلالي: نوع العنصر في الفيديو ← نوع الصوت.
STROKE_BINDING = {
    "text": "scratch",
    "svg": "scratch",
    "highlight": "scratch_soft",
    "underline": "scratch_soft",
    "flourish": "scratch_fast",
    "arrow": "scratch_fast",
    "timeline": "scratch_fast",
    "bars": "scratch_fast",
}
PLACE_BINDING = {
    "paper_card": "page",
    "torn_strip": "page",
    "texture": "page_soft",
    "background": "page_soft",
}
TAP_TYPE = "tick"


def load_calibration() -> dict:
    """جدول المعايرة المقيس (أو {} إن لم يوجد — يُقاس عند الحاجة)."""
    if not CALIBRATION_FILE.exists():
        return {}
    try:
        return json.loads(CALIBRATION_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _load_wav_mono(path: Path, sr: int) -> np.ndarray | None:
    """يقرأ WAV مونو 16بت (يعيد أخذ عينات خطي إن اختلف المعدل)."""
    try:
        with wave.open(str(path), "rb") as w:
            n = w.getnframes()
            ch = w.getnchannels()
            sw = w.getsampwidth()
            rate = w.getframerate()
            raw = w.readframes(n)
    except Exception as exc:  # pragma: no cover
        log.warning("تعذّر قراءة %s: %s", path.name, exc)
        return None
    if sw != 2:
        return None
    data = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    if ch > 1:
        data = data.reshape(-1, ch).mean(axis=1)
    if rate != sr and data.size:
        idx = np.linspace(0, data.size - 1, int(data.size * sr / rate))
        data = np.interp(idx, np.arange(data.size), data).astype(np.float32)
    return data


def library_status() -> dict:
    """هل مكتبة المؤثرات كاملة؟ (فحص رخيص قبل أي رندر)."""
    used = sorted({str(spec.get("source")) for spec in SFX_TYPES.values()})
    missing = [name for name in used if not (SFX_DIR / name).exists()]
    return {
        "types": len(SFX_TYPES),
        "recordings": used,
        "missing": missing,
        "complete": not missing,
        "calibration": bool(load_calibration()),
    }


def _env(n: int, sr: int, attack: float = 0.012, release: float = 0.030) -> np.ndarray:
    env = np.ones(n, dtype=np.float32)
    a = max(1, int(attack * sr))
    r = max(1, int(release * sr))
    if a < n:
        env[:a] = np.linspace(0.0, 1.0, a, dtype=np.float32)
    if r < n:
        env[-r:] *= np.linspace(1.0, 0.0, r, dtype=np.float32)
    return env


def _resample(x: np.ndarray, rate: float) -> np.ndarray:
    """تشغيل أسرع/أبطأ (varispeed) — تغيير الطول والطبقة معًا."""
    if abs(rate - 1.0) < 1e-3 or x.size < 8:
        return x
    n = max(8, int(x.size / rate))
    idx = np.linspace(0, x.size - 1, n)
    return np.interp(idx, np.arange(x.size), x).astype(np.float32)


def _rms_dbfs(x: np.ndarray) -> float:
    if x.size == 0:
        return -120.0
    rms = float(np.sqrt(np.mean(x.astype(np.float64) ** 2)))
    return 20.0 * math.log10(rms) if rms > 0 else -120.0


class SfxLibrary:
    """تسجيلات حقيقية + اشتقاقات منها، كلها بمستوى مقيس."""

    def __init__(self, sr: int = SR, which: str = "ink"):
        self.sr = sr
        self.real = False
        self.sources: list[dict] = []
        self.missing: list[str] = []
        self.calibration = load_calibration()
        self._cache: dict[str, np.ndarray | None] = {}
        self.which = which

    # ---------- التسجيلات ----------
    def recording(self, name: str) -> np.ndarray | None:
        if name not in self._cache:
            path = SFX_DIR / name
            self._cache[name] = _load_wav_mono(path, self.sr) if path.exists() else None
        return self._cache[name]

    def _source_for(self, type_name: str) -> str:
        """The recording behind a type (``which='felt'`` swaps the ink pen)."""
        spec = SFX_TYPES.get(type_name) or {}
        source = str(spec.get("source") or "")
        if self.which == "felt" and type_name in ("scratch", "scratch_fast", "tick"):
            return "pen_felt.wav" if source == "pen_ink.wav" else source
        return source

    # ---------- المستوى ----------
    def _level_to_target(self, seg: np.ndarray, offset_db: float = 0.0) -> tuple[np.ndarray, float]:
        """يعيد المقطع إلى مستوى المكتبة المرجعي (بالقياس، لا بالتخمين)."""
        if seg.size == 0:
            return seg, 0.0
        target = LIBRARY_TARGET_RMS_DBFS + float(offset_db)
        current = _rms_dbfs(seg)
        gain_db = target - current
        scaled = (seg * (10.0 ** (gain_db / 20.0))).astype(np.float32)
        peak = float(np.max(np.abs(scaled))) if scaled.size else 0.0
        limited = 0
        if peak > EVENT_PEAK_CEILING:
            scaled = (scaled * (EVENT_PEAK_CEILING / peak)).astype(np.float32)
            limited = 1
        return scaled, gain_db

    # ---------- الأنواع ----------
    def scratch(self, dur: float, *, type_name: str = "scratch", offset_db: float = 0.0,
                rng: random.Random | None = None) -> np.ndarray:
        """قصّة من تسجيل حقيقي بطول dur، بمستوى مقيس."""
        rng = rng or random
        spec = SFX_TYPES.get(type_name) or SFX_TYPES["scratch"]
        src = self.recording(self._source_for(type_name))
        if src is None or src.size < 64:
            self.missing.append(str(spec.get("source")))
            return np.zeros(0, dtype=np.float32)
        n = max(8, int(dur * self.sr))
        if src.size < n + 64:
            n = max(8, src.size - 64)
        off = rng.randrange(0, max(1, src.size - n))
        seg = _resample(src[off : off + n].copy(), float(spec.get("rate") or 1.0))
        seg = seg * _env(seg.size, self.sr, 0.012, 0.035)
        scaled, _gain = self._level_to_target(seg, offset_db)
        return scaled

    def tick(self, *, offset_db: float = 0.0, rng: random.Random | None = None) -> np.ndarray:
        """نقرة/نقطة: قصّة قصيرة جدًا من التسجيل الحقيقي، بمستوى مقيس."""
        rng = rng or random
        src = self.recording(self._source_for(TAP_TYPE))
        if src is None or src.size < 128:
            self.missing.append(str(SFX_TYPES[TAP_TYPE].get("source")))
            return np.zeros(0, dtype=np.float32)
        n = int(0.032 * self.sr)
        off = rng.randrange(0, max(1, src.size - n))
        seg = src[off : off + n].copy() * _env(n, self.sr, 0.002, 0.022)
        scaled, _gain = self._level_to_target(seg, offset_db)
        return scaled

    def paper(self, dur: float = 0.5, *, type_name: str = "page", offset_db: float = 0.0,
              rng: random.Random | None = None) -> np.ndarray:
        """حركة ورق حقيقية (قلب صفحة) — بدل التوليف."""
        rng = rng or random
        spec = SFX_TYPES.get(type_name) or SFX_TYPES["page"]
        src = self.recording(self._source_for(type_name))
        if src is None or src.size < 256:
            self.missing.append(str(spec.get("source")))
            return np.zeros(0, dtype=np.float32)
        n = max(16, int(dur * self.sr))
        if src.size < n + 64:
            n = max(16, src.size - 64)
        off = rng.randrange(0, max(1, src.size - n))
        seg = _resample(src[off : off + n].copy(), float(spec.get("rate") or 1.0))
        seg = seg * _env(seg.size, self.sr, 0.008, 0.060)
        scaled, _gain = self._level_to_target(seg, offset_db)
        return scaled


def _events_from_json(path: Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        data = {"events": data}
    # The renderer records both the absolute project clock and the
    # output-relative clock. SFX must follow the output, especially for a
    # scene-range preview where the two differ.
    events = []
    for event in data.get("events") or []:
        if not isinstance(event, dict):
            continue
        if event.get("output_t") is not None:
            event = dict(event)
            event["project_t"] = event.get("t")
            event["t"] = event["output_t"]
        events.append(event)
    data["events"] = events
    return data


def _bind_stroke(el_type: str | None) -> str:
    return STROKE_BINDING.get(str(el_type or ""), "scratch")


def _bind_place(el_type: str | None) -> str:
    return PLACE_BINDING.get(str(el_type or ""), "page_soft")


def build_track(sfx_json: str | Path, out_wav: str | Path, *, preset: str = "paper",
                duration: float | None = None, which: str = "ink") -> dict:
    """يبني مسار WAV من أحداث الرسم + ربط دلالي + مستوى مقيس.

    تقرير الإخراج يذكر: عدد الأحداث حسب النوع، مستوى المسار المقيس، ذروته،
    وأي نوع سقط إلى التوليف (لا يوجد توليف صامت: الغياب يُعلن).
    """
    data = _events_from_json(Path(sfx_json))
    events = [e for e in (data.get("events") or []) if isinstance(e, dict)]
    if duration is None:
        duration = max([float(e.get("t", 0.0)) for e in events] + [0.0]) + 1.2
    duration = max(0.0, float(duration))
    lib = SfxLibrary(which=which)
    spec = PRESETS.get(preset, PRESETS["paper"])
    offset_db = float(spec.get("offset_db", 0.0))
    rng = random.Random(20261019)
    n_total = int(duration * SR) + SR // 2
    buf = np.zeros(n_total, dtype=np.float32)

    def put(a: np.ndarray, t: float) -> bool:
        if a is None or a.size == 0:
            return False
        i0 = max(0, int(t * SR))
        i1 = min(n_total, i0 + len(a))
        if i1 > i0:
            buf[i0:i1] += a[: i1 - i0]
            return True
        return False

    downs: list[dict] = []
    counts: dict[str, int] = {}
    dropped = 0
    for e in sorted(events, key=lambda x: float(x.get("t", 0.0))):
        kind = e.get("kind")
        try:
            t = float(e.get("t", 0.0))
        except (TypeError, ValueError):
            dropped += 1
            continue
        if not math.isfinite(t) or t < -0.001 or t > duration:
            # لا نسمح لخط زمني قديم/جزئي بإنتاج صوت خارج الفيلم.
            dropped += 1
            continue
        t = max(0.0, min(t, duration))
        if kind == "down":
            downs.append({"t": t, "e": e})
        elif kind == "up":
            # اربط بآخر down معلّق: مدة الضغطة = الفرق الزمني
            if downs:
                d = downs.pop(0)
                start = float(d["t"])
                end = min(t, duration)
                dur = max(0.03, min(1.6, end - start))
                type_name = _bind_stroke(d["e"].get("el_type"))
                ok = put(lib.scratch(dur, type_name=type_name, offset_db=offset_db, rng=rng), start)
                counts[type_name] = counts.get(type_name, 0) + (1 if ok else 0)
        elif kind == "tap":
            ok = put(lib.tick(offset_db=offset_db, rng=rng), t)
            counts[TAP_TYPE] = counts.get(TAP_TYPE, 0) + (1 if ok else 0)
        elif kind == "place":
            type_name = _bind_place(e.get("el_type"))
            ok = put(lib.paper(0.42, type_name=type_name, offset_db=offset_db, rng=rng), t)
            counts[type_name] = counts.get(type_name, 0) + (1 if ok else 0)
        elif kind == "complete":
            pass

    # A partial render can end while the pen is still down. Close those strokes
    # at the film boundary instead of silently dropping the sound or extending it.
    open_closed = 0
    for d in downs:
        start = float(d["t"])
        end = min(duration, start + 0.25)
        if end <= start:
            continue
        type_name = _bind_stroke(d["e"].get("el_type"))
        ok = put(lib.scratch(max(0.03, end - start), type_name=type_name, offset_db=offset_db, rng=rng), start)
        counts[type_name] = counts.get(type_name, 0) + (1 if ok else 0)
        open_closed += 1

    peak = float(np.max(np.abs(buf))) if buf.size else 0.0
    limiter = 0
    if peak > TRACK_PEAK_CEILING:
        buf *= TRACK_PEAK_CEILING / peak
        limiter = 1
    out = Path(out_wav)
    out.parent.mkdir(parents=True, exist_ok=True)
    pcm = np.clip(buf * 32767.0, -32768, 32767).astype(np.int16)
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())

    missing = sorted(set(lib.missing))
    info = {
        "out": str(out),
        "duration": round(len(buf) / SR, 3),
        "requested_duration": round(duration, 3),
        "events": len(events),
        "counts_by_type": dict(sorted(counts.items())),
        "types_used": len(counts),
        "types_available": len(SFX_TYPES),
        "dropped_events": dropped,
        "closed_open_strokes": open_closed,
        "preset": preset,
        "preset_offset_db": offset_db,
        "sfx_mix_db": spec.get("sfx_mix_db"),
        "library_target_rms_dbfs": LIBRARY_TARGET_RMS_DBFS,
        "track_rms_dbfs": round(_rms_dbfs(buf), 2),
        "track_peak_dbfs": round(20.0 * math.log10(peak), 2) if peak > 0 else -120.0,
        "limiter_engaged": bool(limiter),
        "missing_recordings": missing,
        "synthetic_fallback": bool(missing),
        "real_recordings": not missing,
        "sources": [
            {
                "file": str(spec.get("source")),
                "role": str(spec.get("role")),
                "description": str(spec.get("description")),
            }
            for spec in sorted(SFX_TYPES.values(), key=lambda s: str(s.get("source")))
        ],
    }
    log.info(
        "مؤثرات: %s → %s%s",
        " · ".join(f"{k}={v}" for k, v in info["counts_by_type"].items()) or "لا أحداث",
        out.name,
        " ⚠ توليف بديل" if missing else "",
    )
    return info


def _has_audio_stream(video: Path, ffprobe: str) -> bool:
    import subprocess

    try:
        proc = subprocess.run(
            [ffprobe, "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", str(video)],
            capture_output=True, text=True,
        )
        return bool(proc.stdout.strip())
    except Exception:
        return False


def _probe_duration(video: Path, ffprobe: str) -> float | None:
    import subprocess

    try:
        proc = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(video)],
            capture_output=True, text=True,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return float(proc.stdout.strip())
    except Exception:
        pass
    return None


def mux_into(video: str | Path, sfx_wav: str | Path, out: str | Path, *,
             sfx_weight: float = 0.35, narration: str | Path | None = None,
             duration: float | None = None) -> dict:
    """يدمج المسار في الفيديو (نسخ الفيديو بلا إعادة ترميز).

    - إن كان داخل الفيديو مسار صوت (تعليق سبق دمجه): نخلطه مع المؤثرات.
    - إن مُرّر narration صراحة: يُخلط معه (ولا يُعدّل الملف الأصلي).
    - وإلا: يُضاف المسار وحده.
    - **المزج بأوزان معلومة:** التعليق بوزن 1.0 والمؤثرات بوزن قابل للضبط
      (0.35 خطي ≈ ‎-9.1 dB)، ولا يُعدَّل ملف التعليق الأصلي إطلاقًا.

    Always cuts the output at the video's duration. The old ``-shortest``
    could trim video when narration was shorter; now a short narration fails
    validation instead of silently shortening the picture.
    """
    import subprocess

    from ..render.video import require_ffmpeg

    sfx_weight = max(0.0, min(1.0, float(sfx_weight)))
    ff = require_ffmpeg()
    sibling = Path(ff).with_name("ffprobe.exe")
    if not sibling.exists():
        sibling = Path(ff).with_name("ffprobe")
    ffprobe = str(sibling) if sibling.exists() else "ffprobe"
    video = Path(video)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.stem + ".mux.mp4")
    if duration is None:
        duration = _probe_duration(video, ffprobe)

    inputs = ["-i", str(video)]
    if narration and Path(narration).exists():
        inputs += ["-i", str(narration)]
        inputs += ["-i", str(sfx_wav)]
        narration_idx = 1
        sfx_idx = 2
        has_nar = True
    else:
        inputs += ["-i", str(sfx_wav)]
        narration_idx = None
        sfx_idx = 1
        has_nar = _has_audio_stream(video, ffprobe)

    cut = ["-t", f"{float(duration):.9f}"] if duration and duration > 0 else []
    if has_nar:
        base = f"[{narration_idx}:a]" if narration_idx is not None else "[0:a]"
        fc = (f"{base}aformat=channel_layouts=stereo,volume=1.0[nar];"
              f"[{sfx_idx}:a]aformat=channel_layouts=stereo,volume={sfx_weight}[sfx];"
              f"[nar][sfx]amix=inputs=2:duration=longest:normalize=0[aout]")
        cmd = ([ff, "-y", "-v", "error", *inputs, "-filter_complex", fc,
                "-map", "0:v", "-map", "[aout]", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", *cut, str(tmp)])
        mode = "narration+sfx"
    else:
        cmd = ([ff, "-y", "-v", "error", *inputs, "-map", "0:v", "-map", f"{sfx_idx}:a",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", *cut, str(tmp)])
        mode = "sfx-only"
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg mux فشل: {proc.stderr.strip()[:400]}")
    tmp.replace(out)
    return {
        "out": str(out),
        "mode": mode,
        "sfx_weight": sfx_weight,
        "narration": str(narration) if narration else None,
        "duration": duration,
    }
