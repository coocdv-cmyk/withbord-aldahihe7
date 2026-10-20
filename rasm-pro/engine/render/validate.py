"""تحقق مخرجات الفيديو بفحص FFprobe — لا ادعاء نجاح بلا دليل رقمي.

يفحص: وجود المسارات، الكوديك، الأبعاد، معدل الإطارات (ككسر)، المدة، ومطابقة
الصوت للفيديو. يعيد تقريرًا صريحًا ``ok=True/False`` مع سبب كل فحص.
"""
from __future__ import annotations

import json
import subprocess
from fractions import Fraction
from pathlib import Path

from ..audio.probe import ffprobe_path, require_ffprobe
from ..core.timebase import FrameRate, TimebaseError, coerce_frame_rate, frame_rate_json


class ValidationError(RuntimeError):
    """تعذّر فحص الملف."""


def _frac_rate(txt) -> Fraction | None:
    try:
        s = str(txt or "").strip()
        if not s or s in ("0/0", "0"):
            return None
        if "/" in s:
            n, d = s.split("/", 1)
            n, d = int(n), int(d)
            return Fraction(n, d) if d else None
        return Fraction(s)
    except Exception:
        return None


def ffprobe_media(path: str | Path) -> dict:
    cmd = [
        require_ffprobe(),
        "-v", "error",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=180)
    except FileNotFoundError as e:
        raise ValidationError("ffprobe غير متاح") from e
    if p.returncode != 0:
        raise ValidationError(f"ffprobe فشل: {p.stderr.decode('utf-8', 'replace')[-400:]}")
    try:
        return json.loads(p.stdout.decode("utf-8", "replace"))
    except Exception as e:
        raise ValidationError(f"مخرجات ffprobe غير مفهومة: {e}") from e


def validate_video(
    path: str | Path,
    *,
    expect_size: tuple[int, int] | None = None,
    expect_fps: int | float | str | dict | FrameRate | Fraction | None = None,
    expect_frames: int | None = None,
    expect_audio: bool | None = None,
    expect_duration_sec: float | Fraction | str | None = None,
    tolerance_frames: int = 1,
) -> dict:
    """يفحص ملف فيديو ويعيد تقريرًا كاملًا (لا يرفع استثناء عند فشل فحص)."""
    p = Path(path)
    checks: list[dict] = []

    def check(name: str, ok: bool, detail: str) -> None:
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    if not p.exists():
        return {"ok": False, "path": str(p), "checks": [{"check": "exists", "ok": False, "detail": "الملف غير موجود"}]}
    st = p.stat()
    check("exists", st.st_size > 0, f"{st.st_size} بايت")

    info = ffprobe_media(p)
    streams = info.get("streams") or []
    v = next((s for s in streams if s.get("codec_type") == "video"), None)
    a = next((s for s in streams if s.get("codec_type") == "audio"), None)

    check("video-stream", v is not None, f"{v.get('codec_name') if v else 'لا يوجد'}")
    rate_for_tolerance: Fraction | None = None
    if v:
        w, h = int(v.get("width") or 0), int(v.get("height") or 0)
        if expect_size:
            check("size", (w, h) == (int(expect_size[0]), int(expect_size[1])), f"{w}x{h}")
        fps_actual = _frac_rate(v.get("avg_frame_rate")) or _frac_rate(v.get("r_frame_rate"))
        exp_rate = None
        if expect_fps is not None:
            try:
                exp_rate = coerce_frame_rate(expect_fps)
            except TimebaseError:
                check("fps", False, f"معدل متوقع غير صالح: {expect_fps!r}")
            else:
                check("fps", fps_actual == exp_rate.value, f"{fps_actual} (متوقع {exp_rate})")
        nb = int(v.get("nb_frames") or 0)
        if expect_frames is not None:
            check("frames", nb == int(expect_frames), f"{nb} (متوقع {expect_frames})")
        dur_txt = v.get("duration") or (info.get("format") or {}).get("duration")
        dur = Fraction(str(dur_txt)) if dur_txt else None
        rate_for_tolerance = fps_actual or (exp_rate.value if exp_rate is not None else None)
        if expect_duration_sec is not None and dur is not None and rate_for_tolerance:
            exp_d = Fraction(str(expect_duration_sec)) if not isinstance(expect_duration_sec, Fraction) else expect_duration_sec
            tol = Fraction(int(tolerance_frames)) / rate_for_tolerance
            check(
                "duration",
                abs(dur - exp_d) <= tol,
                f"{float(dur):.3f}ث (متوقع {float(exp_d):.3f}ث ± {float(tol):.3f}ث)",
            )
        rep_v = {
            "codec": v.get("codec_name"),
            "width": w,
            "height": h,
            "fps": str(fps_actual),
            "fps_rate": frame_rate_json(FrameRate(fps_actual.numerator, fps_actual.denominator)) if fps_actual else None,
            "frames": nb,
            "duration_sec": float(dur) if dur else None,
        }
    else:
        rep_v = {}

    if expect_audio is not None:
        check("audio-present", (a is not None) == bool(expect_audio), f"{a.get('codec_name') if a else 'لا يوجد'}")
    if a and v:
        ad = Fraction(str(a.get("duration") or (info.get("format") or {}).get("duration") or "0"))
        vd_txt = v.get("duration") or (info.get("format") or {}).get("duration")
        if vd_txt:
            vd = Fraction(str(vd_txt))
            diff = abs(ad - vd)
            tol = Fraction(int(tolerance_frames)) / rate_for_tolerance if rate_for_tolerance else Fraction(1, 10)
            check("audio-video-duration", diff <= tol, f"فرق {float(diff):.3f}ث (حد {float(tol):.3f}ث)")
        rep_a = {"codec": a.get("codec_name"), "sample_rate": a.get("sample_rate"), "channels": a.get("channels"), "duration_sec": float(ad)}
    else:
        rep_a = {}

    return {
        "ok": all(c["ok"] for c in checks),
        "path": str(p),
        "size_bytes": st.st_size,
        "video": rep_v,
        "audio": rep_a,
        "checks": checks,
    }
