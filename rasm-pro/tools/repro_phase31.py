# -*- coding: utf-8 -*-
"""Phase 3.1 — Milestone 1: إعادة إنتاج عيوب الكتابة العربية بالأرقام والصور.

يعمل قبل/بعد الإصلاح:  --tag before | after

المخرجات في qa/phase31_repro/<tag>/:
- diagnostics.json      أرقام قاطعة: قفزات خاطئة (تخبط/طفرات)، أعداد المسارات،
                        بدايات صحيحة (يمين-أولًا)، سماكات، أزمنة بناء.
- order_<id>.png        خريطة ترتيب الرسم (تدرّج قوس قزح) + علامات حمراء عند
                        أي خط مستقيم يُرسم عبر الفراغ (خلفية الإطار).
- draw_<id>_NN.png      لقطات تدرّج الرسم بالمحرّك الحقيقي (Whiteboard+DocCursor).
- film_<t>.png          إطارات من الفيلم الحالي (مرجع بصري).

تشغيل (من جذر rasm-pro):
    .venv\\Scripts\\python.exe tools\\repro_phase31.py --tag before
"""
from __future__ import annotations

import argparse
import colorsys
import json
import math
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import numpy as np
from PIL import Image, ImageDraw

from engine.core.util import read_json
from engine.render.canvas import DocCursor, Whiteboard, make_paper
from engine.render.director import clip_strokes
from engine.strokes import find_font, text_to_strokes

PLAN = ROOT / "projects" / "ww1" / "storyboard" / "plan.json"
FILM = ROOT / "projects" / "ww1" / "render" / "preview.mp4"
FFMPEG = Path(r"D:\withbord inmation\studio\runtime\ffmpeg.exe")

TELEPORT_PX = 3.0  # أي قفزة داخلية أكبر من كذا بكسل = خط مستقيم غير طبيعي


def _hue(i: int, n: int) -> tuple[int, int, int]:
    r, g, b = colorsys.hsv_to_rgb((i / max(n - 1, 1)) * 0.83, 0.95, 0.92)
    return int(r * 255), int(g * 255), int(b * 255)


def analyze_doc(name: str, strokes, build_sec: float, mask_stats: dict | None = None) -> dict:
    """قياسات قاطعة على مستند مسارات واحد."""
    steps: list[float] = []
    teleports: list[dict] = []
    starts_ok = 0
    brushes: list[float] = []
    prof_mins: list[float] = []
    prof_maxs: list[float] = []
    for si, st in enumerate(strokes):
        jumps = set(st.jumps or [])
        prev = None
        for i, p in enumerate(st.points):
            if prev is not None and (i not in jumps):
                d = math.dist(prev, p)
                steps.append(d)
                if d > TELEPORT_PX:
                    teleports.append(
                        {
                            "stroke": si,
                            "index": i,
                            "dist_px": round(d, 1),
                            "from": [round(v, 1) for v in prev],
                            "to": [round(v, 1) for v in p],
                        }
                    )
            prev = p
        x0, _, x1, _ = st.bbox
        if st.points and x1 > x0 and st.points[0][0] >= x1 - 0.30 * (x1 - x0):
            starts_ok += 1
        brushes.append(st.brush)
        if st.brush_profile:
            prof_mins.append(min(st.brush_profile))
            prof_maxs.append(max(st.brush_profile))
    arr = np.asarray(steps, dtype=np.float64) if steps else np.zeros(1)
    n = len(strokes)
    order_dump = []
    for si, st in enumerate(strokes[:60]):
        x0, y0, x1, y1 = st.bbox
        order_dump.append(
            {
                "i": si,
                "x0": round(x0, 1),
                "x1": round(x1, 1),
                "cy": round((y0 + y1) / 2, 1),
                "points": len(st.points),
                "subpaths": len(st.jumps or []) + 1,
                "first": [round(v, 1) for v in (st.points[0] if st.points else [])],
            }
        )
    return {
        "name": name,
        "build_seconds": round(build_sec, 2),
        "strokes": n,
        "subpaths": int(sum(len(s.jumps or []) + 1 for s in strokes)),
        "points": int(sum(len(s.points) for s in strokes)),
        "median_step_px": round(float(np.median(arr)), 3),
        "p99_step_px": round(float(np.percentile(arr, 99)), 3),
        "teleport_segments_gt3px": len(teleports),
        "teleport_worst": sorted(teleports, key=lambda t: -t["dist_px"])[:10],
        "starts_rightmost_ratio": round(starts_ok / n, 3) if n else None,
        "brush_median": round(float(np.median(brushes)), 2) if brushes else None,
        "profile_min": round(min(prof_mins), 2) if prof_mins else None,
        "profile_max": round(max(prof_maxs), 2) if prof_maxs else None,
        "stroke_order": order_dump,
        **(mask_stats or {}),
    }


def order_map(name: str, doc_strokes, out_png: Path) -> None:
    """خريطة ترتيب الرسم: لون كل مقطع حسب ترتيبه العالمي + علامات الطفرات."""
    xs = [p[0] for s in doc_strokes for p in s.points]
    ys = [p[1] for s in doc_strokes for p in s.points]
    if not xs:
        return
    x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
    W, H = 2200, 760
    m = 60
    s = min((W - 2 * m) / max(x1 - x0, 1), (H - 2 * m) / max(y1 - y0, 1))
    ox = (W - (x1 - x0) * s) / 2 - x0 * s
    oy = (H - (y1 - y0) * s) / 2 - y0 * s

    # كل المقاطع المرسومة بترتيبها العالمي
    segs: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for st in doc_strokes:
        jumps = set(st.jumps or [])
        for i in range(len(st.points) - 1):
            if (i + 1) in jumps:
                continue
            segs.append((tuple(st.points[i]), tuple(st.points[i + 1])))
    img = Image.new("RGB", (W, H), "#FFFFFF")
    d = ImageDraw.Draw(img)
    n = max(len(segs), 1)
    for i, (a, b) in enumerate(segs):
        col = _hue(i, n)
        d.line(
            ((a[0] * s + ox, a[1] * s + oy), (b[0] * s + ox, b[1] * s + oy)),
            fill=col,
            width=3,
        )
    # طفرات: دوائر حمراء
    tps = []
    for st in doc_strokes:
        jumps = set(st.jumps or [])
        for i in range(len(st.points) - 1):
            if (i + 1) in jumps:
                continue
            a, b = st.points[i], st.points[i + 1]
            if math.dist(a, b) > TELEPORT_PX:
                tps.append((a, b))
    for a, b in tps:
        mx, my = (a[0] + b[0]) / 2 * s + ox, (a[1] + b[1]) / 2 * s + oy
        d.ellipse((mx - 14, my - 14, mx + 14, my + 14), outline="#D11", width=4)
    d.text((12, 12), f"{name} | segments={len(segs)} | teleports={len(tps)} (red circles)", fill="#222")
    img.save(out_png)


def progressive(name: str, strokes, out_dir: Path) -> None:
    """لقطات تدرّج الرسم عبر مسار المحرّك الحقيقي (Whiteboard + DocCursor)."""
    if not strokes:
        return
    xs = [p[0] for s in strokes for p in s.points]
    ys = [p[1] for s in strokes for p in s.points]
    x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
    pad = 80
    W = int(min(2300, (x1 - x0) + 2 * pad))
    H = int(min(900, (y1 - y0) + 2 * pad))
    # لوحة بفضاء المستند نفسه (مع إزاحة)
    wb = Whiteboard(int(x1 - x0 + 2 * pad), int(y1 - y0 + 2 * pad), paper=make_paper(int(x1 - x0 + 2 * pad), int(y1 - y0 + 2 * pad)))
    shift = [[[p[0] - x0 + pad, p[1] - y0 + pad] for p in s.points] for s in strokes]
    from engine.strokes.model import Stroke

    shifted = []
    for st, pts in zip(strokes, shift):
        shifted.append(
            Stroke(points=pts, lengths=list(st.lengths), brush=st.brush, kind=st.kind, color=st.color,
                   brush_profile=st.brush_profile, jumps=st.jumps, meta=st.meta)
        )
    cur = DocCursor(shifted)
    for frac in (0.2, 0.45, 0.7, 0.9, 1.0):
        segs = cur.advance(frac)
        wb.paint(segs)
        out = out_dir / f"draw_{name}_{int(frac * 100):03d}.png"
        img = wb.rgb.copy()
        if img.width > W or img.height > H:
            sc = min(W / img.width, H / img.height)
            img = img.resize((int(img.width * sc), int(img.height * sc)), Image.LANCZOS)
        img.save(out)


def extract_film_frames(out_dir: Path) -> None:
    if not FILM.exists() or not FFMPEG.exists():
        return
    fd = out_dir / "film"
    fd.mkdir(parents=True, exist_ok=True)
    for t in (3.0, 9.5, 15.5, 25.5, 33.0, 42.5):
        out = fd / f"film_{t:05.1f}.png"
        if out.exists():
            continue
        subprocess.run(
            [str(FFMPEG), "-y", "-loglevel", "error", "-ss", str(t), "-i", str(FILM), "-frames:v", "1", str(out)],
            check=False,
        )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="before", choices=["before", "after"])
    args = ap.parse_args()

    out_dir = ROOT / "qa" / "phase31_repro" / args.tag
    out_dir.mkdir(parents=True, exist_ok=True)

    plan = read_json(PLAN)
    scenes = {int(s["id"]): s for s in plan["scenes"]}

    targets = [
        ("s1-title", 1, 0),
        ("s1-sub", 1, 1),
        ("s2-tag", 2, 0),
        ("s3-title", 3, 0),
    ]

    results = []
    for name, sid, eidx in targets:
        el = scenes[sid]["elements"][eidx]
        if el.get("type") != "text":
            continue
        font = find_font(el.get("font") or "arefruqaa")
        t0 = time.time()
        doc = text_to_strokes(
            el.get("text", ""),
            font,
            float(el.get("size") or 120),
            mode=el.get("mode", "skeleton"),
            rtl=bool(el.get("rtl", True)),
        )
        build = time.time() - t0
        strokes = clip_strokes(doc, el["rect"])
        print(f"[{name}] بني في {build:.1f}ث · {len(strokes)} مسار")

        res = analyze_doc(name, strokes, build)
        results.append(res)

        order_map(name, strokes, out_dir / f"order_{name}.png")
        progressive(name, strokes, out_dir)

    extract_film_frames(out_dir)

    (out_dir / "diagnostics.json").write_text(
        json.dumps({"tag": args.tag, "targets": results}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("\n== ملخص ==")
    for r in results:
        print(
            f"  {r['name']}: مسارات {r['strokes']} · أجزاء {r['subpaths']} · "
            f"طفرات>{TELEPORT_PX:g}px: {r['teleport_segments_gt3px']} · "
            f"بدايات يمينية {r['starts_rightmost_ratio']} · بناء {r['build_seconds']}ث"
        )
    print(f"\nالمخرجات: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
