# -*- coding: utf-8 -*-
"""قياس أداء Phase 3.1 — تخفيف الخط + أنبوب النص + الكاش + الرندر.

يقيس (بأرقام حقيقية على هذا الجهاز):
  1. Zhang-Suen مقابل Guo-Hall: زمن التخفيف + عدد المكوّنات المتصلة (السبب الجذري للتفتّت).
  2. أنبوب النص (تشكيل+تخانة+مسار) بارد مقابل ساخن (كاش القرص).
  3. تجهيز مشاهد خطة ww1 v2 بارد/ساخن + نسبة إصابة الكاش + ذروة الذاكرة.
تشغيل: .venv\\Scripts\\python.exe tools\\perf_phase31.py
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from engine.core import paths as core_paths  # noqa: E402
from engine.strokes import model as strokes_model  # noqa: E402
from engine.strokes.thinning import guo_hall, thin, zhang_suen  # noqa: E402
from engine.strokes.raster import raster_to_strokes  # noqa: E402
from engine.strokes.text_paths import text_to_strokes  # noqa: E402
from engine.strokes import find_font  # noqa: E402
from engine.render import director as director_mod  # noqa: E402

OUT = ROOT / "qa" / "phase31_perf"
OUT.mkdir(parents=True, exist_ok=True)
RESULT: dict = {}


def components(mask: np.ndarray) -> int:
    """عدد المكوّنات المتصلة (8-جوار) — تنفيذ بسيط بلا مكتبات.

    8-جوار هو المقياس الصحيح لاتصال الهيكل: خط بسماكة بكسل واحد يمرّ قطريًا
    يكون موصولًا بثمانية الجوار لا بأربعته.
    """
    m = mask.astype(bool).copy()
    h, w = m.shape
    seen = np.zeros_like(m)
    count = 0
    stack: list[tuple[int, int]] = []
    ys, xs = np.nonzero(m)
    for y0, x0 in zip(ys.tolist(), xs.tolist()):
        if seen[y0, x0]:
            continue
        count += 1
        stack.append((y0, x0))
        seen[y0, x0] = True
        while stack:
            y, x = stack.pop()
            for ny in (y - 1, y, y + 1):
                for nx in (x - 1, x, x + 1):
                    if 0 <= ny < h and 0 <= nx < w and m[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        stack.append((ny, nx))
    return count


def bench_thinning() -> None:
    rows = []
    # (أ) حلقة رفيعة 5px — حالة التفتّت المقيسة في التقرير
    ring = Image.new("L", (220, 220), 0)
    d = ImageDraw.Draw(ring)
    d.ellipse([40, 40, 180, 180], outline=255, width=5)
    ring_mask = np.asarray(ring) > 127
    # (ب) كلمة عربية حقيقية (تُشكّل عبر أنبوب النص ثم تُرسم كقناع)
    font = find_font("arefruqaa")
    doc = text_to_strokes("الحرب", font, 200, mode="skeleton", rtl=True)
    wm = Image.new("L", (1400, 460), 0)
    wd = ImageDraw.Draw(wm)
    for st in doc.strokes:
        wd.line([tuple(p) for p in st.points], fill=255, width=max(2, int(st.brush)))
    word_mask = np.asarray(wm) > 127
    # (ج) قناع صورة فوتوغرافية (تتبّع صورة) — بمسار raster_to_strokes
    img = Image.open(ROOT / "projects" / "ww1" / "assets" / "event-معركة-السوم" / "c75888b731eb.jpg").convert("L")

    cases = [("ring_5px", ring_mask), ("word_الحرب", word_mask)]
    for name, mask in cases:
        rec = {"case": name, "px": int(mask.sum())}
        t0 = time.perf_counter()
        zs, it = zhang_suen(mask)
        t1 = time.perf_counter()
        gh, ghit = thin(mask)
        t2 = time.perf_counter()
        rec["zhang_suen_s"] = round(t1 - t0, 4)
        rec["zhang_suen_iter"] = it
        rec["zhang_suen_components"] = components(zs)
        rec["guo_hall_s"] = round(t2 - t1, 4)
        rec["guo_hall_iter"] = ghit
        rec["guo_hall_components"] = components(gh)
        rows.append(rec)

    # زمن raster_to_strokes الكامل لصورة (يتضمن الثنائية + التخفيف + المسار)
    t0 = time.perf_counter()
    rdoc = raster_to_strokes(np.asarray(img.convert("RGB")), max_size=900)
    t1 = time.perf_counter()
    rows.append({"case": "raster_900px_photo", "px": int(img.width * img.height),
                 "raster_to_strokes_s": round(t1 - t0, 3), "strokes": len(rdoc.strokes)})
    RESULT["thinning"] = rows


def bench_text(warm_cache: bool) -> dict:
    sentence = "في صيف عام 1914، اشتعلت الحرب العالمية الأولى بعد اغتيال الأرشيدوق فرانز فرديناند في سراييفو."
    font = find_font("arefruqaa")
    director_mod.CACHE_STATS["hit"] = 0
    director_mod.CACHE_STATS["miss"] = 0
    tracemalloc.start()
    t0 = time.perf_counter()
    docs = []
    for i in range(3):  # 3 نصوص مختلفة = 3 مفاتيح كاش
        text = sentence + (" " * i)
        docs.append(director_mod._cached_doc(
            f"text|perf|{text}|200|skeleton|True|{font}",
            lambda t=text: text_to_strokes(t, font, 200, mode="skeleton", rtl=True)))
    t1 = time.perf_counter()
    cur, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {"phase": "warm" if warm_cache else "cold", "seconds": round(t1 - t0, 3),
            "peak_mem_mb": round(peak / 1024 / 1024, 1),
            "cache_hit": director_mod.CACHE_STATS["hit"], "cache_miss": director_mod.CACHE_STATS["miss"],
            "strokes": [len(d.strokes) for d in docs]}


def bench_scene_prep(tmp_cache: Path | None) -> dict:
    """زمن تجهيز مشاهد plan_v2 (تشكيل+تتبّع+تجهيز القوالب) — بارد أو ساخن."""
    from engine.render.director import Director

    plan = json.loads((ROOT / "projects" / "ww1" / "storyboard" / "plan_v2.json").read_text(encoding="utf-8"))
    if tmp_cache is not None:
        strokes_model.CACHE = tmp_cache
        director_mod.CACHE_STATS["hit"] = 0
        director_mod.CACHE_STATS["miss"] = 0
    else:
        strokes_model.CACHE = core_paths.CACHE
        director_mod.CACHE_STATS["hit"] = 0
        director_mod.CACHE_STATS["miss"] = 0
    d = Director(plan, canvas=(2560, 1440), out_size=(1280, 720), fps=24)
    per_scene = []
    t_all = time.perf_counter()
    tracemalloc.start()
    for sc in plan["scenes"]:
        t0 = time.perf_counter()
        items = d._prepare_scene(sc)
        per_scene.append(round(time.perf_counter() - t0, 3))
    t_all = time.perf_counter() - t_all
    cur, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    s = director_mod.CACHE_STATS
    total = s["hit"] + s["miss"]
    return {"per_scene_s": per_scene, "total_s": round(t_all, 3),
            "peak_mem_mb": round(peak / 1024 / 1024, 1),
            "cache_hit": s["hit"], "cache_miss": s["miss"],
            "cache_hit_rate": round(s["hit"] / total, 3) if total else None}


def bench_render(project_id: str = "stage6-arabic-sample", size=(1280, 720)) -> dict:
    """يقيس زمن الرندر **بالفعل** (لا رقم مكتوب).

    الرقم القديم (90.9ث) كان **حرفيًّا مكتوبًا في الأداة** لا قياسًا؛ لذلك
    هذا القسم لا يعمل إلا بطلب صريح: ``tools\\perf_phase31.py render <project>``.
    """
    from engine.render import Director

    pd = core_paths.PROJECTS / project_id
    plan_path = None
    story = pd / "storyboard"
    for name in ("plan_v3.json", "plan_v2.json", "plan.json"):
        candidate = story / name
        if candidate.exists():
            plan_path = candidate
            break
    if plan_path is None:
        return {"error": f"no plan found for {project_id}"}
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    out = Path(tempfile.mkdtemp(prefix="rasm_perf_render_")) / "render.mp4"
    director = Director(
        plan,
        canvas=tuple(plan.get("canvas") or [2560, 1440]),
        out_size=size,
        project_dir=pd,
    )
    t0 = time.time()
    result = director.render(out)
    elapsed = time.time() - t0
    frames = int(result.get("frames") or 0)
    return {
        "project": project_id,
        "plan": str(plan_path.relative_to(ROOT)),
        "frames": frames,
        "seconds_of_film": round(float(result.get("seconds") or 0.0), 3),
        "render_seconds": round(elapsed, 3),
        "fps_effective": round(frames / elapsed, 2) if elapsed else None,
        "note": "measured in-process (Director only, without the SFX mux)",
        "measured_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


def main() -> int:
    section = (sys.argv[1] if len(sys.argv) > 1 else "all").lower()
    perf_json = OUT / "perf.json"
    if perf_json.exists():
        try:
            RESULT.update(json.loads(perf_json.read_text(encoding="utf-8")))
        except Exception:
            pass

    if section in ("all", "thinning"):
        print("== 1) التخفيف (Zhang-Suen مقابل Guo-Hall) ==")
        bench_thinning()
        for r in RESULT["thinning"]:
            print("  ", r)

    if section in ("all", "text"):
        print("== 2) أنبوب النص: بارد ثم ساخن ==")
        tmp = Path(tempfile.mkdtemp(prefix="rasm_cache_"))
        strokes_model.CACHE = tmp
        cold = bench_text(warm_cache=False)
        warm = bench_text(warm_cache=True)
        strokes_model.CACHE = core_paths.CACHE  # نعود لكاش المشروع
        print("  ", cold)
        print("  ", warm)
        RESULT["text_pipeline"] = {"cold": cold, "warm": warm}
        shutil.rmtree(tmp, ignore_errors=True)

    if section in ("all", "scene"):
        print("== 3) تجهيز مشاهد ww1 v2: بارد (كاش فارغ) ثم ساخن ==")
        tmp2 = Path(tempfile.mkdtemp(prefix="rasm_cache2_"))
        cold_sc = bench_scene_prep(tmp2)
        warm_sc = bench_scene_prep(None)
        print("  cold:", cold_sc)
        print("  warm:", warm_sc)
        RESULT["scene_prep"] = {"cold": cold_sc, "warm": warm_sc}
        shutil.rmtree(tmp2, ignore_errors=True)

    if section in ("all", "render"):
        print("== 4) الرندر الفعلي ==")
        if section == "all":
            # the render takes minutes: it is measured only on request, never
            # written from a literal.
            print(
                "  (skipped — قياس الرندر يحتاج وقتًا: "
                "tools\\perf_phase31.py render <project>)"
            )
        else:
            project_id = sys.argv[2] if len(sys.argv) > 2 else "stage6-arabic-sample"
            render = bench_render(project_id)
            print("  ", render)
            RESULT["render"] = render

    perf_json.write_text(json.dumps(RESULT, ensure_ascii=False, indent=1), encoding="utf-8")
    print("✔", perf_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
