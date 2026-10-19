# -*- coding: utf-8 -*-
"""مختبر الجودة العربي — Phase 3.1 (`qa_arabic`).

مجموعات:
  A حروف مفردة (28 + همزة/مدّ)
  B وصل: 28 كلمة حقيقية تغطي أشكال الوصل لكل حرف
  C نقاط الإعجام (1/2/3 نقاط)
  D حركات وتشكيل
  E ≥20 كلمة شائعة
  F ≥10 جمل (قصيرة→طويلة)
  G اتجاه مختلط (عربي + أرقام/لاتيني)
  H نص طويل متعدد الأسطر
  I إطارات تحريك (رسم تدريجي — يُحفظ صورًا)
  J أحداث القلم + تحقق ملامسة السنّ (دقتان/لوحتان)

لكل حالة: قياسات فعلية:
  - teleports: مقاطع غير قفز طولها > 3px في فضاء الرسم (يجب 0)
  - rtl_start: نسبة مسارات تبدأ من يمين صندوقها (للكلمات العربية)
  - coverage/IoU: تغطية الحبر المرسوم لمرجع الحروف المملوءة (نفس الخط/التشكيل)
  - fallback: عدد الكلمات التي سقطت لوضع المحيط (يجب 0)
النتيجة: qa/phase31_lab/report.json + summary.md + لوحات g*.png
"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import numpy as np
import cv2
from PIL import Image, ImageDraw
from scipy import ndimage as ndi

from engine.render.canvas import Whiteboard
from engine.render.director import clip_strokes
from engine.strokes import find_font, text_to_strokes
from engine.strokes.hand_timeline import HandTimeline

OUT = ROOT / "qa" / "phase31_lab"
OUT.mkdir(parents=True, exist_ok=True)

FONT = "arefruqaa"
FONT2 = "amiri"

LETTERS = list("ابتثجحخدذرزسشصضطظعغفقكلمنهوي")
WORDS_JOIN = [
    "أمل", "باب", "بيت", "ثوب", "جبل", "حبل", "خبز", "دار", "ذهب", "رجل", "زيت",
    "سماء", "شمس", "صبر", "ضوء", "طريق", "ظل", "عين", "غيم", "فيل", "قلم", "كتاب",
    "ليل", "ماء", "نهر", "هواء", "ورق", "يد",
]
DOTS = ["بيت", "ثعبان", "تحت", "نجوم", "يحمل", "جدا", "خلال", "ذئب", "زهرة", "شيخ", "ضوء", "ظل", "غزال", "فيل", "قلم"]
DIACRITICS = ["كَتَبَ", "الطَّالِبُ", "مُعَلِّمٌ", "فَتْحَة وَضَمَّة", "جِدًّا", "شَدَّة وَكَسْرَة"]
WORDS20 = ["الحرب", "العالمية", "الأولى", "الجنود", "الخنادق", "الجبهة", "الغربية", "معركة", "السوم",
           "ألمانيا", "الغواصات", "السفن", "التجارية", "المحيط", "الأطلسي", "الولايات", "المتحدة",
           "الحلفاء", "معاهدة", "فرساي", "تعويضات", "خسائر", "البشرية", "مليون", "قتيل"]
SENTENCES = [
    "في صيف عام 1914، اشتعلت الحرب العالمية الأولى.",
    "حفر الجنود الخنادق على الجبهة الغربية.",
    "استخدمت ألمانيا الغواصات لإغراق السفن التجارية.",
    "في عام 1917، دخلت الولايات المتحدة الحرب إلى جانب الحلفاء.",
    "وقّعت ألمانيا معاهدة فرساي في يونيو 1919، وفرضت عليها تعويضات ضخمة.",
    "كانت خسائر الحرب البشرية نحو سبعة عشر مليون قتيل.",
    "رسمت هذه الحرب خريطة الشرق الأوسط من جديد، وأسست عصبة الأمم.",
    "هكذا انتهى عصر الإمبراطوريات وبدأ القرن العشرون بوجه جديد.",
    "سقطت الدولة العثمانية بعد الحرب وتفككت الإمبراطوريات الأربع الكبرى.",
    "بعد اغتيال الأرشيدوق فرانز فرديناند في سراييفو، تسارعت الأحداث نحو حرب شاملة غير مسبوقة في تاريخ البشرية.",
]
MIXED = ["في عام 1914", "الحرب 1914-1918", "King George الخامس", "United States دخلت"]
LONG_TEXT = (
    "في صيف عام 1914، اشتعلت الحرب العالمية الأولى بعد اغتيال الأرشيدوق فرانز فرديناند في سراييفو. "
    "كانت الإمبراطورية الألمانية والنمسا والمجر في مواجهة بريطانيا وفرنسا وروسيا.\n"
    "حفر الجنود الخنادق على الجبهة الغربية في معركة السوم وفردان، فتحولت الحرب إلى حرب استنزاف طويلة."
)

TOL_TELEPORT = 3.0


def _raster_ink(strokes, W, H):
    wb = Whiteboard(W, H, paper=Image.new("RGB", (W, H), (255, 255, 255)))
    tl = HandTimeline(strokes)
    wb.paint(tl.advance(1.0), ink=(20, 20, 20))
    arr = np.asarray(wb.rgb, dtype=np.uint8)
    return arr.mean(axis=2) < 180  # 180: يشمل حواف التمليس الرقيقة (الخطوط الشعرية)


def _fidelity(doc_skel, doc_ref, rect, W, H):
    """تغطية/IoU في إطار مشترك: توضّع التتبّع + إزاحة تطبيع المرجع نفسها.

    كلا المستندين طُبّعا مستقلًا (أصل عند أصغر إحداثي للحبر)، فنعيد المرجع
    إلى إطار التتبّع عبر فرق إزاحتي التطبيع المسجّلتين في stats.
    """
    sw, sh = float(doc_skel.width or 1), float(doc_skel.height or 1)
    k = min(rect[2] / sw, rect[3] / sh)
    ox = rect[0] + (rect[2] - sw * k) / 2.0
    oy = rect[1] + (rect[3] - sh * k) / 2.0
    sk_off = (doc_skel.stats or {}).get("norm_offset") or [0.0, 0.0]
    rf_off = (doc_ref.stats or {}).get("norm_offset") or [0.0, 0.0]
    dx, dy = rf_off[0] - sk_off[0], rf_off[1] - sk_off[1]

    ref_big = np.zeros((H * 2, W * 2), dtype=np.uint8)
    n_poly = 0
    groups: dict[object, list] = {}
    for st in doc_ref.strokes:
        for poly in (st.meta.get("fill") or []):
            if len(poly) >= 3:
                gi = (st.meta or {}).get("gi", id(st))
                groups.setdefault(gi, []).append(poly)
    for gi, polys in groups.items():
        gmask = np.zeros((H * 2, W * 2), dtype=np.uint8)
        for poly in polys:
            # دقة مضاعفة: يمنع ابتلاع الخطوط الشعرية (<1px) عند التقريب الصحيح
            arr = np.array([[int(round((p[0] * k + ox + dx * k) * 2)), int(round((p[1] * k + oy + dy * k) * 2))] for p in poly], dtype=np.int32)
            tmp = np.zeros((H * 2, W * 2), dtype=np.uint8)
            cv2.fillPoly(tmp, [arr], 1)
            gmask ^= tmp  # even-odd داخل الحرف: الثقوب تُستبعد
            n_poly += 1
        ref_big |= gmask   # OR بين الحروف: وصلات الكتابة المتداخلة تبقى حبرًا
    ref = ref_big.reshape(H, 2, W, 2).max(axis=(1, 3)).astype(bool)

    strokes = clip_strokes(doc_skel, rect)
    ink = _raster_ink(strokes, W, H)
    inter = int((ink & ref).sum())
    union = int((ink | ref).sum())

    # مقاييس مبنية على بيانات المعايرة (انظر PHASE3_1_ARABIC_TESTS.md):
    # - cov_tol: تغطية صارمة (1.5px) — تُسجّل للإفصاح، القلم أحادي السماكة لا يعبّئ
    #   الرقعة السميكة كاملة (حد فيزيائي موثّق).
    # - cov_struct: تغطية بنيوية — كل بكسل مرجعي على مسافة ≤ max(2.5px, 3 وحدات مستند)
    #   من الحبر المرسوم (فحص «هل يوجد الهيكل/الشكل في مكانه؟»؛ خط مفقود يفشل).
    # - prec_tol: دقة — نسبة الحبر المرسوم القريب من مرجع (لا حبر شارد).
    # - skel_near_ref: ≤2px — فحص محاذاة (يسمح بشقوق تقطيع 1px على الحدود).
    tol = 1.5
    tol_struct = max(2.5, 3.0 * k)
    dist_to_ink = ndi.distance_transform_edt(~ink)
    dist_to_ref = ndi.distance_transform_edt(~ref)
    ref_d = ref & (dist_to_ink <= tol)
    ink_d = ink & (dist_to_ref <= tol)
    cov_tol = float(ref_d[ref].mean()) if int(ref.sum()) else 0.0
    prec_tol = float(ink_d[ink].mean()) if int(ink.sum()) else 0.0
    cov_struct = float((dist_to_ink[ref] <= tol_struct).mean()) if int(ref.sum()) else 0.0
    inter_t = int(ref_d.sum())
    union_t = int((ref | ink).sum())

    pts = [(ox + p[0] * k, oy + p[1] * k) for st in doc_skel.strokes for p in st.points]
    inside = 0
    near = 0
    for px_, py_ in pts:
        xi = min(max(int(round(px_)), 0), W - 1)
        yi = min(max(int(round(py_)), 0), H - 1)
        if ref[yi, xi]:
            inside += 1
        if dist_to_ref[yi, xi] <= 2.0:
            near += 1
    n_pts = max(len(pts), 1)

    return {
        "coverage": round(inter / max(int(ref.sum()), 1), 3),
        "iou": round(inter / max(union, 1), 3),
        "cov_tol": round(cov_tol, 4),
        "prec_tol": round(prec_tol, 4),
        "cov_struct": round(cov_struct, 4),
        "skel_in_ref": round(inside / n_pts, 4),
        "skel_near_ref": round(near / n_pts, 4),
        "iou_tol": round(inter_t / max(union_t, 1), 3),
        "ref_polys": n_poly,
    }


def _measure(doc, rect=None, W=0, H=0):
    """قياسات موضوعية بإحداثيات المستند (مستقلة عن مقياس الرسم):
    طفرات/بدايات يمينية/قطع.
    """
    strokes = doc.strokes
    teleports = 0
    for st in strokes:
        jumps = set(st.jumps or [])
        pts = st.points
        for i in range(len(pts) - 1):
            if (i + 1) in jumps:
                continue
            if math.dist(pts[i], pts[i + 1]) > 2.0:
                teleports += 1
    rtl_total = 0
    rtl_ok = 0
    for st in strokes:
        if not st.meta.get("rtl"):
            continue
        pts = st.points
        if not pts:
            continue
        x0 = min(p[0] for p in pts)
        x1 = max(p[0] for p in pts)
        if x1 - x0 < 8:
            continue
        rtl_total += 1
        if pts[0][0] >= x0 + 0.5 * (x1 - x0):
            rtl_ok += 1
    return {
        "strokes": len(strokes),
        "pieces": int(sum(len(s.jumps or []) + 1 for s in strokes)),
        "teleports": teleports,
        "rtl_start_ok": (round(rtl_ok / rtl_total, 3) if rtl_total else None),
        "rtl_strokes": rtl_total,
    }


def run_case(gid, text, *, font=FONT, size=240, rect=None, mode="skeleton", rtl=True, fidelity=True, W=1500, H=420):
    rect = rect or [40, 40, W - 80, H - 80]
    t0 = time.time()
    doc = text_to_strokes(text, find_font(font), size, mode=mode, rtl=rtl)
    build = time.time() - t0
    m = _measure(doc)
    m["build_sec"] = round(build, 3)
    m["fallback_tokens"] = int(doc.stats.get("fallback_tokens") or 0)
    m["glyph_strokes"] = int(len(doc.strokes))
    m["dots"] = int(doc.stats.get("dots") or 0)
    if fidelity:
        doc_ref = text_to_strokes(text, find_font(font), size, mode="outline", rtl=rtl)
        m.update(_fidelity(doc, doc_ref, rect, W, H))
    ok = (m["teleports"] == 0) and (m["fallback_tokens"] == 0)
    if fidelity:
        ok = (ok and m.get("cov_struct", 0) >= 0.85 and m.get("prec_tol", 0) >= 0.80
              and m.get("skel_near_ref", 0) >= 0.97)
    m["pass"] = bool(ok)
    return doc, m


def tile(cases, cols=4, cell=(380, 130)):
    rows = int(math.ceil(len(cases) / cols))
    out = Image.new("RGB", (cols * cell[0], rows * cell[1]), (255, 255, 255))
    d = ImageDraw.Draw(out)
    for i, (label, im) in enumerate(cases):
        r, c = divmod(i, cols)
        im2 = im.resize(cell, Image.LANCZOS)
        out.paste(im2, (c * cell[0], r * cell[1]))
        d.rectangle((c * cell[0], r * cell[1], (c + 1) * cell[0] - 1, (r + 1) * cell[1] - 1), outline=(210, 210, 210))
        d.text((c * cell[0] + 6, r * cell[1] + 4), label, fill=(150, 30, 20))
    return out


def trace_image(doc, rect, W=1500, H=420):
    strokes = clip_strokes(doc, rect)
    wb = Whiteboard(W, H, paper=Image.new("RGB", (W, H), (248, 244, 234)))
    tl = HandTimeline(strokes)
    wb.paint(tl.advance(1.0), ink=(34, 30, 26))
    return wb.rgb


def main() -> int:
    report = {"font": FONT, "groups": {}}
    t_all = time.time()

    # ---------- A: حروف مفردة ----------
    cases = []
    rows = []
    for ai, ch in enumerate(LETTERS + ["ء", "آ"], 1):
        doc, m = run_case("A", ch, size=260, W=760, H=460, rect=[40, 40, 680, 380])
        m.update({"group": "A", "text": ch})
        rows.append(m)
        cases.append((f"A{ai:02d}: covT={m.get('cov_tol')} tp={m['teleports']}", trace_image(doc, [40, 40, 680, 380], 760, 460)))
    tile(cases, cols=6, cell=(360, 218)).save(OUT / "gA_letters.png")
    report["groups"]["A"] = rows

    # ---------- B: وصل (28 كلمة) ----------
    cases = []
    rows = []
    for bi, w in enumerate(WORDS_JOIN, 1):
        doc, m = run_case("B", w, size=200, W=860, H=420, rect=[40, 40, 780, 340])
        m.update({"group": "B", "text": w})
        rows.append(m)
        cases.append((f"B{bi:02d}: covT={m.get('cov_tol')}", trace_image(doc, [40, 40, 780, 340], 860, 420)))
    tile(cases, cols=4, cell=(430, 210)).save(OUT / "gB_join.png")
    report["groups"]["B"] = rows

    # ---------- C: نقاط ----------
    cases = []
    rows = []
    for ci, w in enumerate(DOTS, 1):
        doc, m = run_case("C", w, size=220, W=860, H=420, rect=[40, 40, 780, 340])
        m.update({"group": "C", "text": w})
        rows.append(m)
        cases.append((f"C{ci:02d}: dots={m['dots']} covT={m.get('cov_tol')}", trace_image(doc, [40, 40, 780, 340], 860, 420)))
    tile(cases, cols=4, cell=(430, 210)).save(OUT / "gC_dots.png")
    report["groups"]["C"] = rows

    # ---------- D: حركات ----------
    cases = []
    rows = []
    for di, w in enumerate(DIACRITICS, 1):
        doc, m = run_case("D", w, size=200, W=900, H=430, rect=[40, 40, 820, 350])
        m.update({"group": "D", "text": w})
        rows.append(m)
        cases.append((f"D{di:02d}: covT={m.get('cov_tol')}", trace_image(doc, [40, 40, 820, 350], 900, 430)))
    tile(cases, cols=3, cell=(560, 268)).save(OUT / "gD_diacritics.png")
    report["groups"]["D"] = rows

    # ---------- E: ≥20 كلمة ----------
    rows = []
    for w in WORDS20:
        doc, m = run_case("E", w, size=190, W=820, H=380, rect=[40, 40, 740, 300])
        m.update({"group": "E", "text": w})
        rows.append(m)
    report["groups"]["E"] = rows

    # ---------- F: ≥10 جمل ----------
    cases = []
    rows = []
    for fi, s in enumerate(SENTENCES, 1):
        doc, m = run_case("F", s, size=150, W=1720, H=520, rect=[50, 60, 1620, 420])
        m.update({"group": "F", "text": s})
        rows.append(m)
        cases.append((f"F{fi:02d}: covT={m.get('cov_tol')} pieces={m['pieces']}", trace_image(doc, [50, 60, 1620, 420], 1720, 520)))
    tile(cases, cols=1, cell=(1720, 260)).save(OUT / "gF_sentences.png")
    report["groups"]["F"] = rows

    # ---------- G: اتجاه مختلط ----------
    cases = []
    rows = []
    for gi, s in enumerate(MIXED, 1):
        doc, m = run_case("G", s, size=190, W=1200, H=420, rect=[40, 40, 1120, 340], fidelity=False)
        m.update({"group": "G", "text": s})
        rows.append(m)
        cases.append((f"G{gi:02d}: tp={m['teleports']}", trace_image(doc, [40, 40, 1120, 340], 1200, 420)))
    tile(cases, cols=2, cell=(600, 210)).save(OUT / "gG_mixed.png")
    report["groups"]["G"] = rows

    # تحقق خاص: الأرقام تُرسم من اليسار
    doc_dig = text_to_strokes("1914", find_font(FONT), 200, mode="skeleton", rtl=False)
    st0 = doc_dig.strokes[0]
    xs = [p[0] for p in st0.points]
    digits_ltr_ok = st0.points[0][0] < min(xs) + 0.4 * (max(xs) - min(xs))
    report["digits_ltr_first_stroke_left"] = bool(digits_ltr_ok)

    # ---------- H: نص طويل ----------
    doc, m = run_case("H", LONG_TEXT, size=120, W=1500, H=760, rect=[40, 40, 1420, 660], fidelity=True)
    m.update({"group": "H", "text": "long-text"})
    report["groups"]["H"] = [m]
    trace_image(doc, [40, 40, 1420, 660], 1500, 760).save(OUT / "gH_long.png")

    # ---------- I: إطارات تحريك ----------
    doc = text_to_strokes("الحرب العالمية", find_font(FONT), 200, mode="skeleton", rtl=True)
    rect = [40, 60, 1120, 380]
    strokes = clip_strokes(doc, rect)
    tl = HandTimeline(strokes, words=(doc.stats or {}).get("words"))
    frames = []
    for pct in (0, 15, 35, 55, 75, 90, 100):
        wb = Whiteboard(1200, 480, paper=Image.new("RGB", (1200, 480), (248, 244, 234)))
        wb.paint(tl.advance(pct / 100.0), ink=(34, 30, 26))
        frames.append((f"I:{pct}%", wb.rgb))
    tile(frames, cols=2, cell=(600, 240)).save(OUT / "gI_anim.png")
    report["groups"]["I"] = [{"frames": [0, 15, 35, 55, 75, 90, 100], "note": "رسم تدريجي عبر خط الزمن"}]

    # ---------- J: أحداث القلم + تحقق الملامسة ----------
    j_rows = []
    doc = text_to_strokes("بسم الله", find_font(FONT2), 190, mode="skeleton", rtl=True)
    rect = [60, 80, 1100, 320]
    strokes = clip_strokes(doc, rect)
    tl = HandTimeline(strokes, words=(doc.stats or {}).get("words"))
    evs = tl.events
    downs = [e for e in evs if e.kind == "down"]
    ups = [e for e in evs if e.kind == "up"]
    taps = [e for e in evs if e.kind == "tap"]
    balanced = abs(len(downs) - len(ups)) <= 0 and (len(downs) + len(taps)) > 0
    seq_ok = True
    state = "up"
    for e in evs:
        if e.kind == "down" and state == "down":
            seq_ok = False
        if e.kind == "up" and state == "up":
            seq_ok = False
        if e.kind in ("down", "up"):
            state = e.kind
    j_rows.append({"check": "event_balance", "downs": len(downs), "ups": len(ups), "taps": len(taps), "pass": bool(balanced)})
    j_rows.append({"check": "state_machine_order", "pass": bool(seq_ok)})

    # ملامسة السنّ: (أ) داخل اللوحة على دقتين — (ب) عبر كاميرا حقيقية (تصغير/تكبير/إزاحة)
    # و(ج) مع دوران القلم بزوايا مختلفة: موضع الطرف يجب أن يبقى على الحبر في كل حالة.
    from engine.render.camera import Viewport, crop_resize  # noqa: E402
    from engine.render.director import Director  # noqa: E402

    contact = []
    for (W, H) in ((1280, 720), (960, 540)):
        # نرسم حتى منتصف الزمن ثم نتحقق أن موضع tip على الحبر
        wb = Whiteboard(W, H, paper=Image.new("RGB", (W, H), (248, 244, 234)))
        tl2 = HandTimeline(strokes, words=(doc.stats or {}).get("words"))
        segs = tl2.advance(0.5)
        tip = tl2.tip()
        wb.paint(segs, ink=(20, 20, 20))
        arr = np.asarray(wb.rgb, dtype=np.uint8)
        dark = np.argwhere(arr.mean(axis=2) < 90)
        if tip is not None and len(dark):
            d2 = np.sqrt(((dark[:, 0] - tip[1]).astype(np.float64)) ** 2 + ((dark[:, 1] - tip[0]).astype(np.float64)) ** 2)
            contact.append({"res": f"{W}x{H}", "dist_px": round(float(d2.min()), 2), "pass": bool(d2.min() <= 3.0)})
        else:
            contact.append({"res": f"{W}x{H}", "dist_px": None, "pass": False})
    j_rows.extend(contact)

    # (ب+ج) كاميرا حقيقية (نفس دوال المخرج) + دوران القلم حول طرفه
    pen_dir = Director({"canvas": [2560, 1440], "scenes": []}, canvas=(2560, 1440), out_size=(1280, 720), fps=24)
    # الكاميرا المكبّرة تُبنى حول موضع الطرف الفعلي (فتُبقيه داخل الإطار) — كما يفعل
    # fit_viewport في المخرج (قصّ/تحجيم داخل حدود اللوحة).
    tl_probe = HandTimeline(strokes, words=(doc.stats or {}).get("words"))
    tl_probe.advance(0.5)
    tip_probe = tl_probe.tip() or (1280.0, 720.0)
    zw, zh = 1200.0, 675.0
    zx = min(max(tip_probe[0] - zw / 2, 0.0), 2560.0 - zw)
    zy = min(max(tip_probe[1] - zh / 2, 0.0), 1440.0 - zh)
    cams = [
        ("لوحة كاملة", Viewport(0.0, 0.0, 2560.0, 1440.0), (1280, 720)),
        ("لوحة كاملة مصغّرة", Viewport(0.0, 0.0, 2560.0, 1440.0), (960, 540)),
        ("كاميرا مكبّرة حول الطرف", Viewport(zx, zy, zw, zh), (1280, 720)),
    ]
    for cam_name, cam, (W, H) in cams:
        cw2, ch2 = 2560, 1440
        wb2 = Whiteboard(cw2, ch2, paper=Image.new("RGB", (cw2, ch2), (248, 244, 234)))
        tl3 = HandTimeline(strokes, words=(doc.stats or {}).get("words"))
        wb2.paint(tl3.advance(0.5), ink=(20, 20, 20))
        tip = tl3.tip()
        base = crop_resize(wb2.rgb, cam, (W, H)).convert("RGB")
        barr = np.asarray(base, dtype=np.uint8)
        dark2 = np.argwhere(barr.mean(axis=2) < 90)
        if tip is None or not dark2.size:
            j_rows.append({"check": f"contact|{cam_name}", "res": f"{W}x{H}", "dist_px": None, "pass": False})
            continue
        # نفس معادلة إسقاط الطرف المستخدمة في المخرج
        tipx = (tip[0] - cam.x) * (W / cam.w)
        tipy = (tip[1] - cam.y) * (H / cam.h)
        ix, iy = int(round(tipx)), int(round(tipy))
        dmin = float(np.sqrt((dark2[:, 0] - tipy) ** 2 + (dark2[:, 1] - tipx) ** 2).min())
        for ang in (35.0, 95.0, 190.0, 300.0):
            pen_dir.out_size = (W, H)
            pen_dir.pen_angle = float(ang)
            pen_dir.pen_prev = None  # زاوية ثابتة: نختبر الدوران حول الطرف نفسه
            frame = base.copy()
            pen_dir._draw_pen(frame, {"obj": tl3}, cam)
            farr = np.asarray(frame, dtype=np.uint8)
            covered = bool(0 <= ix < W and 0 <= iy < H and not np.array_equal(farr[iy, ix], barr[iy, ix]))
            j_rows.append({
                "check": f"contact|{cam_name}|قلم {int(ang)}°",
                "res": f"{W}x{H}",
                "dist_px": round(dmin, 2),
                "tip_covered": covered,
                "pass": bool(dmin <= 3.0 and covered),
            })
    report["groups"]["J"] = j_rows

    # ---------- K: نصوص الفيلم v2 حرفيًّا (كما وردت في plan_v2.json بفواصل أسطرها) ----------
    k_rows = []
    k_cases = []
    plan_path = ROOT / "projects" / "ww1" / "storyboard" / "plan_v2.json"
    if plan_path.exists():
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        seen = set()
        for sc in plan.get("scenes", []):
            for el in sc.get("elements", []):
                txt = el.get("text")
                if el.get("type") != "text" or not txt:
                    continue
                font = el.get("font") or "arefruqaa"
                size = float(el.get("size") or 200)
                key = (txt, font, size)
                if key in seen:
                    continue
                seen.add(key)
                doc_k, m = run_case("K", txt, font=font, size=size, W=1600, H=460, rect=[40, 40, 1520, 380])
                m.update({"group": "K", "text": txt.replace("\n", " / "), "font": font, "size": size})
                k_rows.append(m)
                if len(k_cases) < 12:
                    k_cases.append((f"K{len(k_rows):02d}: covS={m.get('cov_struct')}", trace_image(doc_k, [40, 40, 1520, 380], 1600, 460)))
        tile(k_cases, cols=2, cell=(760, 230)).save(OUT / "gK_filmtexts.png")
    report["groups"]["K"] = k_rows

    # ---------- ملخص ----------
    all_cases = []
    for g, rows_g in report["groups"].items():
        if isinstance(rows_g, list) and rows_g and isinstance(rows_g[0], dict) and "pass" in rows_g[0]:
            all_cases.extend(rows_g)
    passed = sum(1 for r in all_cases if r.get("pass"))
    total = len(all_cases)
    covs = [r.get("cov_tol") for r in all_cases if r.get("cov_tol") is not None]
    structs = [r.get("cov_struct") for r in all_cases if r.get("cov_struct") is not None]
    skels = [r.get("skel_near_ref") for r in all_cases if r.get("skel_near_ref") is not None]
    precs = [r.get("prec_tol") for r in all_cases if r.get("prec_tol") is not None]
    report["summary"] = {
        "cases": total,
        "passed": passed,
        "cov_tol_min": round(min(covs), 4) if covs else None,
        "cov_tol_mean": round(sum(covs) / len(covs), 4) if covs else None,
        "cov_struct_min": round(min(structs), 4) if structs else None,
        "cov_struct_mean": round(sum(structs) / len(structs), 4) if structs else None,
        "prec_tol_min": round(min(precs), 4) if precs else None,
        "skel_near_ref_min": round(min(skels), 4) if skels else None,
        "teleports_total": int(sum(r.get("teleports", 0) for r in all_cases)),
        "fallback_total": int(sum(r.get("fallback_tokens", 0) for r in all_cases)),
        "seconds": round(time.time() - t_all, 1),
    }
    (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")

    # summary.md
    lines = ["# مختبر الجودة العربي — Phase 3.1", "", f"الخط الأساسي: `{FONT}` · الحالات: {total} · ناجحة: {passed}", ""]
    lines.append(f"- تغطية بنيوية (cov_struct، تسامح 3 وحدات مستند) الأدنى: {report['summary']['cov_struct_min']} · المتوسط: {report['summary']['cov_struct_mean']}")
    lines.append(f"- تغطية صارمة (cov_tol، 1.5px — تُسجّل للإفصاح) الأدنى: {report['summary']['cov_tol_min']} · المتوسط: {report['summary']['cov_tol_mean']}")
    lines.append(f"- دقة الحبر المرسوم (prec_tol) الأدنى: {report['summary']['prec_tol_min']} · محاذاة الهيكل (≤2px) الأدنى: {report['summary']['skel_near_ref_min']}")
    lines.append(f"- طفرات: {report['summary']['teleports_total']} · احتياط طباعي: {report['summary']['fallback_total']}")
    lines.append("")
    for g in sorted(report["groups"]):
        rows_g = report["groups"][g]
        if not isinstance(rows_g, list) or not rows_g or not isinstance(rows_g[0], dict):
            continue
        if not any("pass" in r for r in rows_g):
            # مجموعة إفادة (مثل إطارات التحريك) — ليست حالة نجاح/فشل
            lines.append(f"## مجموعة {g}: إفادة ({len(rows_g)} عنصر — بلا حكم)")
            lines.append("")
            continue
        n = len(rows_g)
        p = sum(1 for r in rows_g if r.get("pass"))
        lines.append(f"## مجموعة {g}: {p}/{n}")
        lines.append("")
        lines.append("| # | النص | مسارات | قطع | طفرات | بداية يمينية | cov_struct | cov_tol | prec_tol | محاذاة | نجاح |")
        lines.append("|---|------|--------|-----|-------|--------------|------------|---------|----------|--------|------|")
        for i, r in enumerate(rows_g, 1):
            txt = str(r.get("text", ""))[:34].replace("|", "·")
            lines.append(
                f"| {i} | {txt} | {r.get('strokes','')} | {r.get('pieces','')} | {r.get('teleports','')} | "
                f"{r.get('rtl_start_ok','')} | {r.get('cov_struct','')} | {r.get('cov_tol','')} | {r.get('prec_tol','')} | {r.get('skel_near_ref','')} | {'✔' if r.get('pass') else '✘'} |"
            )
        lines.append("")
    lines.append("## مجموعة I — إطارات التحريك")
    lines.append("مخرجات: `gI_anim.png` (0→100% عبر خط الزمن).")
    lines.append("")
    lines.append("## مجموعة J — أحداث القلم وملامسة السنّ")
    lines.append("")
    lines.append("| فحص | نتيجة | تفصيل |")
    lines.append("|-----|-------|-------|")
    for r in report["groups"]["J"]:
        if "downs" in r or r.get("check") == "state_machine_order":
            lines.append(f"| {r['check']} | {'✔' if r.get('pass') else '✘'} | downs={r.get('downs','')} ups={r.get('ups','')} taps={r.get('taps','')} |")
        elif "check" in r:
            lines.append(f"| {r['check']} | {'✔' if r.get('pass') else '✘'} | {r.get('res')} · أقرب حبر {r.get('dist_px')}px · القلم يغطي الطرف: {r.get('tip_covered')} |")
        else:
            lines.append(f"| ملامسة {r.get('res')} | {'✔' if r.get('pass') else '✘'} | أقرب حبر {r.get('dist_px')}px |")
    (OUT / "summary.md").write_text("\n".join(lines), encoding="utf-8")

    print(f"الحالات: {total} · ناجحة: {passed}")
    print(f"cov_struct: min={report['summary']['cov_struct_min']} mean={report['summary']['cov_struct_mean']} · "
          f"cov_tol_min={report['summary']['cov_tol_min']} · prec_tol_min={report['summary']['prec_tol_min']} · "
          f"skel_near_min={report['summary']['skel_near_ref_min']} · teleports={report['summary']['teleports_total']} · fallback={report['summary']['fallback_total']}")
    print(f"الأرقام LTR أولًا: {report['digits_ltr_first_stroke_left']}")
    print(f"المخرجات: {OUT}")
    return 0 if passed == total else 2


if __name__ == "__main__":
    raise SystemExit(main())
