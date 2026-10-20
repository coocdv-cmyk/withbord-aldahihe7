"""فحص ملفات الصوت بلا تحميلها في الذاكرة: FFprobe + عدّ عينات تدفّقي + بصمة SHA-256.

- ``probe_audio``: وصف كامل (كوديك/معدل/قنوات/مدة كسرية/عدد عينات مضبوط) + قمم
  الموجة لعرض الموجة في الواجهات — كل شيء يقرأ الملف على شكل دفعات (bounded memory).
- عدد العينات يُحسب بفك الترميز تدفّقيًا (ffmpeg → s16le) فلا يعتمد على تقديرات
  الحاوية العشرية.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from array import array
from fractions import Fraction
from pathlib import Path

from ..core.log import get_logger
from ..render.video import _bundle_roots, ffmpeg_path, require_ffmpeg

log = get_logger("audio.probe")

AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".aac", ".ogg", ".oga", ".opus", ".flac", ".wma", ".aiff", ".aif"}


class AudioError(RuntimeError):
    """ملف صوت غير صالح/غير مدعوم أو فشل أداة الفحص."""


def ffprobe_path() -> str | None:
    """Locate ffprobe, or ``None`` when it is not available."""
    env = os.environ.get("RASM_FFPROBE")
    if env and Path(env).exists():
        return str(Path(env))
    for root in _bundle_roots():
        candidate = root / "ffprobe.exe"
        if candidate.exists():
            return str(candidate)
        candidate = root / "ffprobe"
        if candidate.exists():
            return str(candidate)
    return shutil.which("ffprobe")


def require_ffprobe() -> str:
    exe = ffprobe_path()
    if not exe:
        raise AudioError(
            "ffprobe غير موجود. ضعه في runtime/ بجانب التطبيق أو اضبط "
            "RASM_FFPROBE أو أضفه إلى PATH."
        )
    return exe


def sha256_file(path: str | Path, *, chunk: int = 1 << 20) -> str:
    """بصمة الملف تدفّقيًا — ذاكرة ثابتة مهما كبر الملف."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _ffprobe_json(path: Path) -> dict:
    cmd = [
        require_ffprobe(),
        "-v", "error",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=120)
    except FileNotFoundError as e:
        raise AudioError("ffprobe غير متاح") from e
    if p.returncode != 0:
        raise AudioError(f"ffprobe فشل: {p.stderr.decode('utf-8', 'replace')[-300:]}")
    try:
        return json.loads(p.stdout.decode("utf-8", "replace"))
    except Exception as e:
        raise AudioError(f"مخرجات ffprobe غير مفهومة: {e}") from e


def _decode_count_and_peaks(path: Path, sample_rate: int, *, peak_rate: int = 10, chunk_bytes: int = 1 << 18):
    """يفكّ الصوت تدفّقيًا (mono s16le) ويعيد: عدد العينات + قمم موجبة/سالبة.

    لا يحتفظ بأي شيء في الذاكرة أكبر من دفعة واحدة؛ القمم فقط (~peak_rate/ثانية).
    """
    cmd = [
        require_ffmpeg(),
        "-v", "error",
        "-i", str(path),
        "-f", "s16le",
        "-acodec", "pcm_s16le",
        "-ac", "1",
        "-ar", str(sample_rate),
        "-",
    ]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert p.stdout is not None

    per_bucket = max(1, sample_rate // max(1, peak_rate))
    peaks_min: list[float] = []
    peaks_max: list[float] = []
    cur_min = 0
    cur_max = 0
    cur_n = 0
    total = 0
    carry = b""

    def close_bucket():
        nonlocal cur_min, cur_max, cur_n
        peaks_min.append(cur_min / 32768.0)
        peaks_max.append(cur_max / 32768.0)
        cur_min, cur_max, cur_n = 0, 0, 0

    while True:
        buf = p.stdout.read(chunk_bytes)
        if not buf:
            break
        if carry:
            buf = carry + buf
        even = len(buf) - (len(buf) % 2)
        carry = buf[even:]
        if even == 0:
            continue
        arr = array("h")
        arr.frombytes(buf[:even])
        total += len(arr)
        # تقسيم حسب حدود القمم
        idx = 0
        n = len(arr)
        while idx < n:
            take = min(per_bucket - cur_n, n - idx)
            seg = arr[idx : idx + take]
            if seg:
                s_min = min(seg)
                s_max = max(seg)
                if s_min < cur_min:
                    cur_min = s_min
                if s_max > cur_max:
                    cur_max = s_max
            cur_n += take
            idx += take
            if cur_n >= per_bucket:
                close_bucket()
    if cur_n:
        close_bucket()
    p.stdout.close()
    err = b""
    try:
        err = p.stderr.read() if p.stderr else b""
    except Exception:
        pass
    rc = p.wait()
    if rc != 0:
        raise AudioError(f"فك ترميز الصوت فشل (كود {rc}): {err.decode('utf-8', 'replace')[-300:]}")
    return total, peaks_min, peaks_max


def probe_audio(path: str | Path, *, deep: bool = True, peak_rate: int = 10) -> dict:
    """وصف كامل لملف صوت + (اختياريًا) عدّ عينات مضبوط وقمم موجة.

    ``duration`` تُعاد ككسر عشري دقيق من نص ffprobe، و``total_samples`` الدقيق
    يأتي من العدّ التدفّقي لا من ضرب المدة × المعدل.
    """
    p = Path(path)
    if not p.exists():
        raise AudioError(f"ملف غير موجود: {p}")
    if p.suffix.lower() not in AUDIO_EXTS:
        # نجرب الفحص رغم ذلك (قد يكون امتدادًا غريبًا لكن محتواه صوتي)
        log.warning("امتداد غير معتاد للصوت: %s", p.suffix)

    info = _ffprobe_json(p)
    streams = info.get("streams") or []
    astream = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if not astream:
        raise AudioError(f"لا يوجد مسار صوت في: {p.name}")

    sample_rate = int(astream.get("sample_rate") or 0)
    channels = int(astream.get("channels") or 0)
    codec = str(astream.get("codec_name") or "")
    dur_txt = astream.get("duration") or (info.get("format") or {}).get("duration")
    duration = Fraction(str(dur_txt)) if dur_txt else None

    out: dict = {
        "file": p.name,
        "path": str(p.resolve()),
        "bytes": p.stat().st_size,
        "sha256": sha256_file(p),
        "codec": codec,
        "sample_rate": sample_rate,
        "channels": channels,
        "duration": str(duration) if duration is not None else None,
        "duration_sec": float(duration) if duration is not None else None,
        "total_samples_est": (int(duration * sample_rate) if duration is not None and sample_rate else None),
        "deep": False,
    }

    if deep and sample_rate:
        total, pmin, pmax = _decode_count_and_peaks(p, sample_rate, peak_rate=peak_rate)
        out["deep"] = True
        out["total_samples"] = total
        out["peaks_min"] = pmin
        out["peaks_max"] = pmax
        out["peak_rate"] = peak_rate
        out["duration_exact"] = str(Fraction(total, sample_rate))
        if duration is not None:
            # تحقق ذاتي: العدّ التدفّقي يجب أن يطابق مدة الحاوية (± عينة واحدة إلى ثانية واحدة أحيانًا)
            delta = abs(Fraction(total, sample_rate) - duration)
            out["duration_delta_sec"] = float(delta)
    elif duration is not None and sample_rate:
        out["total_samples"] = out["total_samples_est"]

    return out
