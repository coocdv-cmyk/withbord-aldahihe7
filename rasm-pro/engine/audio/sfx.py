"""مؤثرات صوتية من أحداث القلم — تسجيلات حقيقية (ملكية عامة) + توليف احتياطي.

الأسلوب:
- صوت الرسم/الملامسة يُقتطع من تسجيل حقيقي («Writing with inkpen», PDSounds,
  ملكية عامة — انظر assets/sfx/LICENSES.json)، كل مسار = قصّة بطول زمن
  الضغط الحقيقي مع غلاف هجوم/انكسار ناعم → ليس "بيب" ولا نغمة صناعية.
- نقرة/نقطة الإعجام = قصّة قصيرة جدًا (35ms) من نفس التسجيل.
- انزلاق الورق عند بداية المشهد = توليف (ضجيج مرشّح بمغلّف جرسي) لأن التسجيل
  الحقيقي لا يحتوي انزلاقًا — يُوسم صراحة في التقرير.
- إن غابت الملفات الحقيقية: توليف كامل لضجيج ورقي بمستوى مقبول، مع وسم واضح.

الخلط:
- build_track: أحداث المخرج (sfx.json) → WAV مونو 48kHz بعائد ذروة ≤ 0.7.
- مكس مع تعليق صوتي عبر ffmpeg: التعليق بوزن 1.0 والمؤثرات بوزن 0.35
  (لا نعدّل ملف التعليق الأصلي إطلاقًا).
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

PRESETS = {
    "paper":  {"scratch": 0.55, "tick": 0.35, "slide": 0.30},
    "subtle": {"scratch": 0.35, "tick": 0.22, "slide": 0.18},
    "bold":   {"scratch": 0.75, "tick": 0.50, "slide": 0.34},
}


def _load_wav_mono(path: Path, sr: int) -> np.ndarray | None:
    """يقرأ WAV مونو 16بت (يعيد أخذ عينات خطي إن اختلف المعدل)."""
    try:
        with wave.open(str(path), "rb") as w:
            n = w.getnframes()
            ch = w.getnchannels()
            sw = w.getsampwidth()
            rate = w.getframerate()
            raw = w.readframes(n)
        if sw != 2:
            return None
        a = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        if ch > 1:
            a = a.reshape(-1, ch).mean(axis=1)
        if rate != sr and len(a):
            x_old = np.linspace(0.0, 1.0, len(a), endpoint=False)
            x_new = np.linspace(0.0, 1.0, int(len(a) * sr / rate), endpoint=False)
            a = np.interp(x_new, x_old, a).astype(np.float32)
        return a
    except Exception as e:  # pragma: no cover
        log.warning("تعذّر قراءة %s: %s", path.name, e)
        return None


def _env(n: int, sr: int, attack: float = 0.012, release: float = 0.030) -> np.ndarray:
    a = max(1, int(attack * sr))
    r = max(1, int(release * sr))
    up = np.minimum(1.0, np.arange(n) / a)
    dn = np.minimum(1.0, np.arange(n)[::-1] / r)
    return (up * dn).astype(np.float32)


class SfxLibrary:
    """مكتبة أصوات: تسجيلات حقيقية إن وُجدت، وإلا توليف احتياطي."""

    def __init__(self, sr: int = SR, which: str = "ink"):
        self.sr = sr
        self.real = False
        self.sources: list[dict] = []
        self.primary = _load_wav_mono(SFX_DIR / ("pen_felt.wav" if which == "felt" else "pen_ink.wav"), sr)
        self.secondary = _load_wav_mono(SFX_DIR / ("pen_ink.wav" if which == "felt" else "pen_felt.wav"), sr)
        if self.primary is not None and len(self.primary) > sr // 2:
            self.real = True
            self.sources.append({"file": "pen_felt.wav" if which == "felt" else "pen_ink.wav",
                                 "license": "Public domain (PDSounds)", "kind": "recording"})
        else:
            self.sources.append({"file": None, "license": "procedural synthesis", "kind": "synth"})

    # ---------- مكوّنات ----------
    def scratch(self, dur: float, *, gain: float = 1.0, rng: random.Random | None = None) -> np.ndarray:
        """قصّة من تسجيل الكتابة الحقيقي بطول dur (أو توليف ضجيج ورقي)."""
        rng = rng or random
        n = max(8, int(dur * self.sr))
        src = self.primary if (self.primary is not None and len(self.primary) > n + 64) else None
        if src is not None:
            off = rng.randrange(0, len(src) - n)
            seg = src[off:off + n].astype(np.float32).copy()
        else:
            noise = np.random.default_rng(rng.randrange(1 << 30)).normal(0.0, 1.0, n).astype(np.float32)
            # ضجيج ورقي: مرشّح تمرير نطاق تقريبي (فرق مرشّحين أسيّين)
            b = np.empty(n, dtype=np.float32)
            acc = 0.0
            for i in range(n):
                acc += (noise[i] - acc) * 0.55
                b[i] = acc
            seg = (noise - b * 0.85)
        env = _env(n, self.sr, 0.012, 0.035)
        return (seg * env * float(gain)).astype(np.float32)

    def tick(self, *, gain: float = 1.0, rng: random.Random | None = None) -> np.ndarray:
        """نقرة ملامسة قصيرة (نقطة إعجام): عيّنة حقيقية قصيرة أو نقرة ضجيج مخمدة."""
        rng = rng or random
        n = int(0.032 * self.sr)
        src = self.primary if (self.primary is not None and len(self.primary) > n + 64) else None
        if src is not None:
            off = rng.randrange(0, len(src) - n)
            seg = src[off:off + n].astype(np.float32).copy()
        else:
            t = np.arange(n) / self.sr
            f = 1900.0
            seg = (np.random.default_rng(rng.randrange(1 << 30)).normal(0, 0.7, n) * np.exp(-t * 120.0)
                   + np.sin(2 * math.pi * f * t) * np.exp(-t * 260.0) * 0.35).astype(np.float32)
        return (seg * _env(n, self.sr, 0.002, 0.022) * float(gain)).astype(np.float32)

    def paper_slide(self, dur: float = 0.5, *, gain: float = 1.0, rng: random.Random | None = None) -> np.ndarray:
        """انزلاق/انقلاب ورق — توليف (لا يوجد في التسجيل الأصلي)."""
        rng = rng or random
        n = max(16, int(dur * self.sr))
        noise = np.random.default_rng(rng.randrange(1 << 30)).normal(0.0, 1.0, n).astype(np.float32)
        # تمرير عالي تقريبي + مغلّف جرسي
        hp = np.diff(noise, prepend=noise[:1])
        bell = np.sin(np.linspace(0, math.pi, n)) ** 1.6
        return (hp * 0.5 * bell * float(gain)).astype(np.float32)


def _events_from_json(path: Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {"events": data}


def build_track(sfx_json: str | Path, out_wav: str | Path, *, preset: str = "paper",
                duration: float | None = None, which: str = "ink") -> dict:
    """يبني مسار WAV من أحداث القلم (down/up/tap) + انزلاقات بدايات المشاهد."""
    data = _events_from_json(Path(sfx_json))
    events = [e for e in (data.get("events") or []) if isinstance(e, dict)]
    if duration is None:
        duration = max([float(e.get("t", 0.0)) for e in events] + [0.0]) + 1.2
    duration = max(0.0, float(duration))
    lib = SfxLibrary(which=which)
    g = PRESETS.get(preset, PRESETS["paper"])
    rng = random.Random(20261019)
    n_total = int(duration * SR) + SR // 2
    buf = np.zeros(n_total, dtype=np.float32)

    def put(a: np.ndarray, t: float) -> None:
        i0 = max(0, int(t * SR))
        i1 = min(n_total, i0 + len(a))
        if i1 > i0:
            buf[i0:i1] += a[: i1 - i0]

    downs: list[dict] = []
    scratch_count = 0
    tap_count = 0
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
                put(lib.scratch(dur, gain=g["scratch"] * rng.uniform(0.85, 1.15), rng=rng), start)
                scratch_count += 1
        elif kind == "tap":
            put(lib.tick(gain=g["tick"] * rng.uniform(0.85, 1.2), rng=rng), t)
            tap_count += 1
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
        put(lib.scratch(max(0.03, end - start), gain=g["scratch"] * 0.8, rng=rng), start)
        scratch_count += 1
        open_closed += 1

    slide_count = 0
    for sc in data.get("scenes") or []:
        try:
            st = float(sc.get("start") or 0.0)
        except (TypeError, ValueError):
            continue
        if 0.05 < st <= duration:
            put(lib.paper_slide(0.45, gain=g["slide"] * rng.uniform(0.9, 1.1), rng=rng), st - 0.22)
            slide_count += 1

    peak = float(np.max(np.abs(buf))) or 1.0
    if peak > 0.7:
        buf *= 0.7 / peak
    out = Path(out_wav)
    out.parent.mkdir(parents=True, exist_ok=True)
    pcm = np.clip(buf * 32767.0, -32768, 32767).astype(np.int16)
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())

    info = {
        "out": str(out),
        "duration": round(len(buf) / SR, 3),
        "requested_duration": round(duration, 3),
        "events": len(events),
        "scratches": scratch_count,
        "taps": tap_count,
        "slides": slide_count,
        "dropped_events": dropped,
        "closed_open_strokes": open_closed,
        "real_recordings": lib.real,
        "sources": lib.sources,
    }
    log.info("مؤثرات: %d قصّة رسم · %d نقرة · %d انزلاق → %s", scratch_count, tap_count, slide_count, out.name)
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


def mux_into(video: str | Path, sfx_wav: str | Path, out: str | Path, *,
             sfx_weight: float = 0.35, narration: str | Path | None = None) -> dict:
    """يدمج المسار في الفيديو (نسخ الفيديو بلا إعادة ترميز).

    - إن كان داخل الفيديو مسار صوت (تعليق سبق دمجه): نخلطه مع المؤثرات.
    - إن مُرّر narration صراحة: يُخلط معه (ولا يُعدّل الملف الأصلي).
    - وإلا: يُضاف المسار وحده.
    """
    import subprocess

    from ..render.video import ffmpeg_path

    sfx_weight = max(0.0, min(1.0, float(sfx_weight)))
    ff = ffmpeg_path()
    ffprobe = str(Path(ff).with_name("ffprobe.exe")) if Path(ff).with_name("ffprobe.exe").exists() else "ffprobe"
    video = Path(video)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.stem + ".mux.mp4")

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

    if has_nar:
        base = f"[{narration_idx}:a]" if narration_idx is not None else "[0:a]"
        fc = (f"{base}aformat=channel_layouts=stereo,volume=1.0[nar];"
              f"[{sfx_idx}:a]aformat=channel_layouts=stereo,volume={sfx_weight}[sfx];"
              f"[nar][sfx]amix=inputs=2:duration=first:normalize=0[aout]")
        cmd = ([ff, "-y", "-v", "error", *inputs, "-filter_complex", fc,
                "-map", "0:v", "-map", "[aout]", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest", str(tmp)])
        mode = "narration+sfx"
    else:
        cmd = ([ff, "-y", "-v", "error", *inputs, "-map", "0:v", "-map", f"{sfx_idx}:a",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest", str(tmp)])
        mode = "sfx-only"
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg mux فشل: {proc.stderr.strip()[:400]}")
    tmp.replace(out)
    return {"out": str(out), "mode": mode}
