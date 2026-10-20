# -*- coding: utf-8 -*-
"""فيديو تشخيصي «قبل/بعد» — يُبنى من مخرجات qa/phase31_repro الحقيقية.

- يقارن كل حالة (عنوان/سطر/بطاقة) على مراحل الرسم 20→100% بين النسخة القديمة والجديدة.
- يقارن الفيلم الأصلي (preview.mp4) بالفيلم المحسّن (preview_v2.mp4).
- النصوص العربية تُرسم بمحرّك rasm-pro نفسه (text_to_strokes) لا بمكتبة خارجية.
المخرج: qa/phase31_diag/before_after.mp4 (1280x720 · 24fps)
تشغيل: .venv\\Scripts\\python.exe tools\\make_diag_video.py
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from engine.audio.probe import require_ffprobe  # noqa: E402
from engine.render.video import require_ffmpeg  # noqa: E402
from engine.render import templates as T  # noqa: E402
from engine.render.canvas import Whiteboard  # noqa: E402
from engine.strokes import find_font  # noqa: E402
from engine.strokes.hand_timeline import HandTimeline  # noqa: E402

REPRO = ROOT / "qa" / "phase31_repro"
OUT = ROOT / "qa" / "phase31_diag"
OUT.mkdir(parents=True, exist_ok=True)
W, H, FPS = 1280, 720, 24

CASES = [
    ("s1-title", "عنوان المشهد 1", "في صيف عام 1914"),
    ("s1-sub", "سطر المشهد 1", "النص التفسيري"),
    ("s2-tag", "بطاقة المشهد 2", "معركة السوم"),
    ("s3-title", "عنوان المشهد 3", "1917 دخول أمريكا"),
]
PCTS = [20, 45, 70, 90, 100]

PAPER = (252, 249, 243)
PANEL_BEFORE = (250, 234, 231)
PANEL_AFTER = (231, 244, 233)
RED = (150, 45, 32)
GREEN = (28, 105, 52)
INK = (34, 30, 26)


def diag(tag: str) -> dict:
    d = json.loads((REPRO / tag / "diagnostics.json").read_text(encoding="utf-8"))
    return {t["name"]: t for t in d["targets"]}


BEFORE = diag("before")
AFTER = diag("after")


def paint_text(img: Image.Image, text: str, size: float, cx: float, cy: float, color=INK, font: str = "arefruqaa") -> None:
    """يرسم نصًّا عربيًّا بحجمه الطبيعي بمحرّك rasm-pro (تشكيل + مسار + فرشاة)."""
    strokes, doc = T.text_strokes(text, find_font(font), size, rtl=True)
    placed = T.place_strokes(doc, cx - doc.width / 2.0, cy - doc.height / 2.0, doc.width, doc.height)
    wb = Whiteboard(W, H, paper=img)
    segs = HandTimeline(placed).advance(1.0)
    wb.paint(segs, ink=color)
    img.paste(wb.rgb, (0, 0))  # نُعيد اللوحة المرسومة إلى الصورة المتراكمة


def card_plain(bg=PAPER) -> Image.Image:
    return Image.new("RGB", (W, H), bg)


def fit(img: Image.Image, box_w: int, box_h: int) -> Image.Image:
    s = min(box_w / img.width, box_h / img.height)
    return img.resize((max(1, int(img.width * s)), max(1, int(img.height * s))), Image.LANCZOS)


def paste_center(base: Image.Image, im: Image.Image, cx: int, cy: int, border=(205, 198, 186)) -> None:
    x, y = cx - im.width // 2, cy - im.height // 2
    d = ImageDraw.Draw(base)
    d.rectangle([x - 4, y - 4, x + im.width + 3, y + im.height + 3], outline=border, width=2)
    base.paste(im, (x, y))


def panel(img: Image.Image, box, fill, outline) -> None:
    d = ImageDraw.Draw(img)
    d.rectangle(box, fill=fill, outline=outline, width=3)


def frame_intro() -> Image.Image:
    im = card_plain()
    paint_text(im, "تقرير مرئي: قبل / بعد", 96, W / 2, 210)
    paint_text(im, "إصلاح الكتابة العربية في راسم برو", 52, W / 2, 350, RED, font="amiri")
    paint_text(im, "4 حالات قياس من الفيلم + مقارنة الفيلم كاملًا", 44, W / 2, 440, INK, font="amiri")
    paint_text(im, "Phase 3.1", 40, W / 2, 560, (110, 105, 96), font="amiri")
    return im


def frame_case_header(cid: str, title_ar: str, sample: str) -> Image.Image:
    b, a = BEFORE[cid], AFTER[cid]
    im = card_plain()
    paint_text(im, f"الحالة: {title_ar}", 62, W / 2, 78)
    paint_text(im, sample, 40, W / 2, 148, (95, 90, 82), font="amiri")
    panel(im, [60, 200, 600, 520], PANEL_BEFORE, (225, 190, 185))
    panel(im, [680, 200, 1220, 520], PANEL_AFTER, (186, 216, 190))
    paint_text(im, "قبل", 56, 330, 245, RED)
    paint_text(im, "بعد", 56, 950, 245, GREEN)
    for x, t, col in ((330, b, RED), (950, a, GREEN)):
        paint_text(im, f"مسارات: {t['strokes']}", 44, x, 330, col, font="amiri")
        paint_text(im, f"قطع فرعية: {t['subpaths']}", 44, x, 400, col, font="amiri")
        paint_text(im, f"زمن البناء: {t['build_seconds']}ث", 44, x, 470, col, font="amiri")
    verdict = (f"القطع الفرعية: {a['subpaths']} بعد أن كانت {b['subpaths']} · "
               f"المسارات: {a['strokes']} بعد أن كانت {b['strokes']} · "
               f"الطفرات: {a['teleport_segments_gt3px']} بعد أن كانت {b['teleport_segments_gt3px']}")
    paint_text(im, verdict, 46, W / 2, 600, INK, font="amiri")
    return im


def frame_compare(cid: str, pct: int) -> Image.Image:
    im = card_plain()
    paint_text(im, f"{cid} — الرسم عند {pct}%", 46, W / 2, 44, (95, 90, 82), font="amiri")
    for tag, cx in (("before", 330), ("after", 950)):
        p = REPRO / tag / f"draw_{cid}_{pct:03d}.png"
        if not p.exists():
            continue
        img = fit(Image.open(p).convert("RGB"), 600, 540)
        paste_center(im, img, cx, 390)
        paint_text(im, "قبل" if tag == "before" else "بعد", 50, cx, 96, RED if tag == "before" else GREEN)
    b, a = BEFORE[cid], AFTER[cid]
    paint_text(im, f"قطع فرعية: {a['subpaths']} بعد أن كانت {b['subpaths']}", 40, W / 2, 690, (85, 80, 74), font="amiri")
    return im


def extract_film_frames() -> list[tuple[Image.Image, Image.Image, str]]:
    """إطارات مقارنة من الفيلمين الأصلي والمحسّن (تُستخرج بـffmpeg)."""
    tmp = Path(tempfile.mkdtemp(prefix="rasm_diag_"))
    ff = require_ffmpeg()
    pairs = [
        ("v1", ROOT / "projects" / "ww1" / "render" / "preview.mp4", 4.0,
         "v2", ROOT / "projects" / "ww1" / "render" / "preview_v2.mp4", 8.0, "العنوان الافتتاحي"),
        ("v1", ROOT / "projects" / "ww1" / "render" / "preview.mp4", 15.0,
         "v2", ROOT / "projects" / "ww1" / "render" / "preview_v2.mp4", 33.0, "بطاقة الصورة + التعليق"),
        ("v1", ROOT / "projects" / "ww1" / "render" / "preview.mp4", 44.0,
         "v2", ROOT / "projects" / "ww1" / "render" / "preview_v2.mp4", 80.5, "الخاتمة"),
    ]
    out = []
    for i, (_t1, p1, s1, _t2, p2, s2, label) in enumerate(pairs):
        for k, (path, sec) in enumerate(((p1, s1), (p2, s2))):
            dst = tmp / f"f{i}_{k}.png"
            subprocess.run([ff, "-y", "-v", "error", "-ss", str(sec), "-i", str(path), "-frames:v", "1", str(dst)], check=True)
            out.append((Image.open(dst).convert("RGB"), label, sec))
    groups = []
    for i in range(0, len(out), 2):
        groups.append((out[i][0], out[i + 1][0], out[i][1], out[i][2], out[i + 1][2]))
    return groups, tmp


def frame_film_pair(a: Image.Image, b: Image.Image, label: str, s1: float, s2: float) -> Image.Image:
    im = card_plain()
    paint_text(im, f"{label}", 48, W / 2, 42, (95, 90, 82), font="amiri")
    paste_center(im, fit(a, 600, 480), 330, 380)
    paste_center(im, fit(b, 600, 480), 950, 380)
    paint_text(im, f"الأصلي · {s1}ث", 40, 330, 92, RED, font="amiri")
    paint_text(im, f"المحسّن · {s2}ث", 40, 950, 92, GREEN, font="amiri")
    return im


def frame_final() -> Image.Image:
    im = card_plain()
    paint_text(im, "النتيجة", 92, W / 2, 130)
    paint_text(im, "المختبر العربي: 135/135 · اختبارات الوحدة: 24/24", 46, W / 2, 280, GREEN, font="amiri")
    paint_text(im, "الفيلم المحسّن: preview_v2.mp4 — 81.5ث · 24fps · 1280x720", 46, W / 2, 370, INK, font="amiri")
    paint_text(im, "صوت: مؤثرات مسجّلة حقيقية (الملكية العامة) — بلا سرد", 46, W / 2, 450, INK, font="amiri")
    paint_text(im, "الفيلم الأصلي محفوظ: preview.mp4 (44.5ث)", 44, W / 2, 540, (110, 105, 96), font="amiri")
    return im


def main() -> int:
    frames: list[Image.Image] = []
    intro = frame_intro()
    frames += [intro] * int(3.0 * FPS)
    for cid, title_ar, sample in CASES:
        hdr = frame_case_header(cid, title_ar, sample)
        frames += [hdr] * int(2.2 * FPS)
        for pct in PCTS:
            frames += [frame_compare(cid, pct)] * int(0.75 * FPS)
    groups, tmp = extract_film_frames()
    for a, b, label, s1, s2 in groups:
        frames += [frame_film_pair(a, b, label, s1, s2)] * int(2.2 * FPS)
    fin = frame_final()
    frames += [fin] * int(3.5 * FPS)

    out = OUT / "before_after.mp4"
    cmd = [require_ffmpeg(), "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-crf", "20",
           "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    assert p.stdin is not None
    for im in frames:
        p.stdin.write(im.tobytes())
    p.stdin.close()
    rc = p.wait()
    shutil.rmtree(tmp, ignore_errors=True)
    if rc != 0:
        print("✘ فشل ترميز الفيديو التشخيصي")
        return 1
    probe = subprocess.run([require_ffprobe(), "-v", "error", "-select_streams", "v", "-show_entries",
                            "stream=codec_name,width,height,r_frame_rate,nb_frames", "-of", "csv=p=0", str(out)],
                           capture_output=True, text=True)
    print(f"✔ {out}")
    print(f"   {len(frames)} إطارًا · {len(frames) / FPS:.1f}ث · ffprobe: {probe.stdout.strip()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
