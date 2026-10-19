"""قوالب سينمائية مرسومة بيد حرّة — مولّدة برمجيًا بالكامل (بلا أصول خارجية).

ثلاث عائلات:
1. عناصر يد (strokes) تُرسم بخط زمن القلم نفسه: تظليل ماركر، تسطير، سهم،
   خط زمني، أعمدة بيانات، خط مموّج/زخرفة.
2. ديكور ورق (طبقة ثابتة تُرسم على اللوحة): بطاقة صورة بظل وشريط لاصق،
   شريط ورق ممزّق، إطار بولارويد.
3. أدوات نص مصغّرة: وضع وثيقة نص في مستطيل بمحاذاة (للتسميات داخل القوالب).

كل الدوال حتمية بذرة ثابتة (seed) — نفس الخطة = نفس الرسم بالضبط.
"""
from __future__ import annotations

import math
import random
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from ..strokes.model import Stroke

# ---------- أدوات ----------


def _cumulative(pts: list[list[float]]) -> list[float]:
    lengths = [0.0]
    s = 0.0
    for i in range(1, len(pts)):
        s += math.dist(pts[i], pts[i - 1])
        lengths.append(s)
    return lengths


def _stroke(pts: list[list[float]], brush: float, *, profile: list[float] | None = None,
            color: str | None = None, meta: dict | None = None) -> Stroke:
    return Stroke(points=[[float(x), float(y)] for x, y in pts], lengths=_cumulative(pts),
                  brush=float(brush), brush_profile=profile, color=color, meta=meta or {})


def _wobble(n: int, amp: float, seed: int, freq: float = 1.0) -> list[float]:
    """انحراف ناعم (مجموع جيوب) بطول n — حتمي بالبذرة."""
    rng = random.Random(int(seed))
    ph = [rng.random() * math.tau for _ in range(3)]
    out = []
    for i in range(n):
        u = i / max(1, n - 1)
        out.append(amp * (0.6 * math.sin(ph[0] + freq * math.tau * u)
                          + 0.3 * math.sin(ph[1] + 2.3 * freq * math.tau * u)
                          + 0.1 * math.sin(ph[2] + 4.7 * freq * math.tau * u)))
    return out


def _resample(p0, p1, samples: int) -> list[list[float]]:
    return [[p0[0] + (p1[0] - p0[0]) * i / (samples - 1),
             p0[1] + (p1[1] - p0[1]) * i / (samples - 1)] for i in range(samples)]


# ---------- عناصر يد ----------

def hand_line(p0, p1, *, brush: float = 4.0, seed: int = 1, wobble: float = 2.2,
              samples: int = 26, bow: float = 0.0) -> list[Stroke]:
    """خط يدوي: انحراف عمودي + قوس اختياري (bow: نسبة من الطول)."""
    pts = _resample(p0, p1, samples)
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    ln = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / ln, dx / ln
    off = _wobble(samples, wobble, seed)
    for i, o in enumerate(off):
        u = i / (samples - 1)
        b = bow * ln * math.sin(math.pi * u)
        pts[i][0] += nx * (o + b)
        pts[i][1] += ny * (o + b)
    return [_stroke(pts, brush)]


def hand_arrow(p0, p1, *, brush: float = 4.5, seed: int = 2, curve: float = 0.22,
               head: float = 34.0, wobble: float = 2.0) -> list[Stroke]:
    """سهم منحنٍ بيد حرّة مع رأس من ضربتين."""
    p0 = [float(p0[0]), float(p0[1])]
    p1 = [float(p1[0]), float(p1[1])]
    pts = _resample(p0, p1, 30)
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    ln = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / ln, dx / ln
    off = _wobble(30, wobble, seed)
    for i, o in enumerate(off):
        u = i / 29.0
        b = curve * ln * math.sin(math.pi * u)
        pts[i][0] += nx * (o + b)
        pts[i][1] += ny * (o + b)
    shaft = _stroke(pts, brush)
    tipx, tipy = pts[-1]
    ux, uy = pts[-1][0] - pts[-6][0], pts[-1][1] - pts[-6][1]
    ul = math.hypot(ux, uy) or 1.0
    ux, uy = ux / ul, uy / ul
    a = math.radians(155.0)
    heads = []
    for sgn in (1.0, -1.0):
        ra = sgn * a
        hx = ux * math.cos(ra) - uy * math.sin(ra)
        hy = ux * math.sin(ra) + uy * math.cos(ra)
        hp = _resample([tipx, tipy], [tipx + hx * head, tipy + hy * head], 8)
        w = _wobble(8, 1.2, seed + (1 if sgn > 0 else 2))
        for i, o in enumerate(w):
            hp[i][0] += -hy * o
            hp[i][1] += hx * o
        heads.append(_stroke(hp, brush * 0.95))
    return [shaft] + heads


def marker_band(rect, *, brush: float | None = None, seed: int = 11, tilt: float = 0.02,
                color: str | None = None) -> list[Stroke]:
    """شريط تظليل ماركر: مسحة عريضة واحدة بعرض المستطيل (تُرسم وراء النص لاحقًا)."""
    x, y, w, h = [float(v) for v in rect]
    b = float(brush if brush is not None else h * 0.46)
    y0 = y + h * 0.5 - tilt * w
    y1 = y + h * 0.5 + tilt * w
    p0 = [x + w + 12, y0]
    p1 = [x - 12, y1]
    pts = _resample(p0, p1, 22)
    off = _wobble(22, h * 0.06, seed)
    for i, o in enumerate(off):
        pts[i][1] += o
    prof = [b * (0.92 + 0.16 * (0.5 + 0.5 * math.sin(i * 0.9 + seed))) for i in range(len(pts))]
    return [_stroke(pts, b, profile=prof, color=color)]


def underline(rect, *, double: bool = False, brush: float = 4.5, seed: int = 21,
              offset: float = 10.0, color: str | None = None) -> list[Stroke]:
    """تسطير يدوي أسفل المستطيل (1 أو 2 خط)."""
    x, y, w, h = [float(v) for v in rect]
    yb = y + h + offset
    out = hand_line([x + w - 6, yb], [x + 6, yb + 2], brush=brush, seed=seed, wobble=1.6, samples=28)
    if double:
        out += hand_line([x + w - 40, yb + brush * 3.4], [x + 60, yb + brush * 3.4 + 3], brush=brush * 0.8,
                         seed=seed + 5, wobble=1.4, samples=24)
    if color:
        for st in out:
            st.color = color
    return out


def flourish(rect, *, brush: float = 3.4, seed: int = 31, color: str | None = None) -> list[Stroke]:
    """زخرفة توقيع صغيرة (قوس مزدوج) أسفل العنصر."""
    x, y, w, h = [float(v) for v in rect]
    yb = y + h + 16
    pts = []
    n = 40
    for i in range(n):
        u = i / (n - 1)
        px = x + w - 10 - (w - 20) * u
        py = yb + math.sin(math.pi * u * 1.6) * 9 * (1 - 0.4 * u)
        pts.append([px, py])
    off = _wobble(n, 1.3, seed)
    for i, o in enumerate(off):
        pts[i][1] += o
    st = _stroke(pts, brush)
    if color:
        st.color = color
    return [st]


# ---------- تسميات نصية داخل القوالب ----------

def text_strokes(text: str, font_path: Path, size: float, *, rtl: bool = True) -> list[Stroke]:
    from ..strokes.text_paths import text_to_strokes

    doc = text_to_strokes(text, font_path, size, mode="skeleton", rtl=rtl)
    return list(doc.strokes), doc


def place_strokes(doc, x: float, y: float, w: float, h: float, *, anchor: str = "center",
                  valign: str = "middle", scale: float = 1.0) -> list[Stroke]:
    """يُحجّم وثيقة نص في مستطيل بمحاذاة (يحفظ النسبة) — يُعيد مسارات منسوخة.

    مرّر w,h = المقاس الطبيعي للوثيقة للرسم بحجم الخط الأصلي (بلا تضخيم).
    """
    sw, sh = float(doc.width or 1), float(doc.height or 1)
    s = min(w / sw, h / sh) * scale
    ax = {"left": 0.0, "center": 0.5, "right": 1.0}.get(anchor, 0.5)
    ay = {"top": 0.0, "middle": 0.5, "bottom": 1.0}.get(valign, 0.5)
    ox = x + (w - sw * s) * ax
    oy = y + (h - sh * s) * ay
    out: list[Stroke] = []
    for st in doc.strokes:
        pts = [[ox + p[0] * s, oy + p[1] * s] for p in st.points]
        prof = [max(0.7, b * s) for b in st.brush_profile] if st.brush_profile else None
        out.append(Stroke(points=pts, lengths=[l * s for l in st.lengths], brush=max(0.7, st.brush * s),
                          kind=st.kind, color=st.color, brush_profile=prof, jumps=st.jumps,
                          meta=dict(st.meta or {})))
    return out


def timeline_strokes(rect, events: list[dict], *, font_path: Path, size: float = 70,
                     rtl: bool = True, seed: int = 41, brush: float = 5.0,
                     color: str | None = None) -> list[Stroke]:
    """خط زمني مرسوم: محور + علامات + نقطة لكل حدث + تسمية (عنوان/سنة).

    events = [{"label": "1914", "sub": "اندلاع الحرب"}, ...]
    rtl=True: الأقدم يمينًا (اتجاه عربي).
    """
    x, y, w, h = [float(v) for v in rect]
    n = max(1, len(events))
    axis_y = y + h * 0.62
    strokes: list[Stroke] = []
    # المحور
    strokes += hand_line([x + w - 24, axis_y], [x + 24, axis_y], brush=brush, seed=seed,
                         wobble=3.0, samples=64, bow=0.0)
    # مواضع الأحداث
    for i, ev in enumerate(events):
        u = (i / (n - 1)) if n > 1 else 0.5
        fx = (x + w - 60) - (w - 120) * u if rtl else (x + 60) + (w - 120) * u
        # علامة على المحور
        strokes += hand_line([fx, axis_y - 12], [fx, axis_y + 12], brush=brush * 0.85, seed=seed + 3 + i,
                             wobble=1.2, samples=8)
        # دائرة الحدث (قوس مغلق)
        r = 7.0
        circ = []
        for k in range(20):
            a = math.tau * k / 19.0
            circ.append([fx + r * math.cos(a + 0.35), axis_y + r * math.sin(a + 0.35)])
        strokes.append(_stroke(circ, brush * 0.75))
        # التسمية + السطر الفرعي: بحجم الخط الطبيعي (بلا تضخيم لملء الصندوق)،
        # متبادلة أعلى/أسفل المحور؛ كل حدث يحمل سنته وسطره الفرعي معًا.
        label = str(ev.get("label") or "")
        sub = str(ev.get("sub") or "")
        l_doc = s_doc = None
        if label:
            _, l_doc = text_strokes(label, font_path, size, rtl=False)
        if sub:
            _, s_doc = text_strokes(sub, font_path, size * 0.52, rtl=rtl)
        lw = float(getattr(l_doc, "width", 0.0) or 0.0)
        lh = float(getattr(l_doc, "height", 0.0) or 0.0)
        sw2 = float(getattr(s_doc, "width", 0.0) or 0.0)
        sh2 = float(getattr(s_doc, "height", 0.0) or 0.0)
        wid = max(lw, sw2)
        cx = min(max(fx, x + 14 + wid / 2), x + w - 14 - wid / 2)
        stack_h = (lh + (8.0 + sh2 if s_doc else 0.0)) if l_doc else sh2
        up = (i % 2 == 0)
        yy = (axis_y - 34.0 - stack_h) if up else (axis_y + 34.0)
        if l_doc:
            strokes += place_strokes(l_doc, cx - lw / 2, yy, lw, lh, anchor="center", valign="middle")
            yy += lh + 8.0
        if s_doc:
            strokes += place_strokes(s_doc, cx - sw2 / 2, yy, sw2, sh2, anchor="center", valign="middle")
    if color:
        for st in strokes:
            st.color = color
    return strokes


def bars_strokes(rect, values: list[float], labels: list[str], *, font_path: Path, size: float = 60,
                 seed: int = 51, brush: float = 5.0, color: str | None = None,
                 label_size: float | None = None) -> list[Stroke]:
    """أعمدة بيانات مرسومة يدويًا + قيمة/تسمية لكل عمود (ترتيب يسار→يمين)."""
    x, y, w, h = [float(v) for v in rect]
    n = max(1, len(values))
    vmax = max(values) or 1.0
    axis_y = y + h
    strokes: list[Stroke] = []
    strokes += hand_line([x, axis_y], [x + w, axis_y], brush=brush, seed=seed, wobble=3.0, samples=60)
    slot = w / n
    bw = slot * 0.42
    for i, v in enumerate(values):
        bx = x + slot * (i + 0.5) - bw * 0.5
        bh = (h * 0.78) * (v / vmax)
        by = axis_y - bh
        # العمود: ثلاثة خطوط رأسية (يسار/يمين/قمة) — أسلوب رسم يدوي
        strokes += hand_line([bx, axis_y - 4], [bx, by + 6], brush=brush * 0.8, seed=seed + i * 3, wobble=1.6, samples=16)
        strokes += hand_line([bx + bw, axis_y - 4], [bx + bw, by + 6], brush=brush * 0.8, seed=seed + i * 3 + 1, wobble=1.6, samples=16)
        strokes += hand_line([bx - 4, by], [bx + bw + 4, by], brush=brush * 0.85, seed=seed + i * 3 + 2, wobble=1.8, samples=14)
        # قيمة فوق العمود (بحجم الخط الطبيعي — بلا تضخيم)
        vt = f"{int(round(v))}" if float(v).is_integer() else f"{v:g}"
        _, v_doc = text_strokes(vt, font_path, label_size or size * 0.8, rtl=False)
        vw = float(v_doc.width or 0.0)
        vh = float(v_doc.height or 0.0)
        cx = bx + bw / 2.0
        strokes += place_strokes(v_doc, cx - vw / 2, by - 8 - vh, vw, vh, anchor="center", valign="middle")
        if i < len(labels) and labels[i]:
            _, l_doc = text_strokes(labels[i], font_path, size * 0.62, rtl=True)
            lw = float(l_doc.width or 0.0)
            lh = float(l_doc.height or 0.0)
            strokes += place_strokes(l_doc, cx - lw / 2, axis_y + 12, lw, lh, anchor="center", valign="middle")
    if color:
        for st in strokes:
            st.color = color
    return strokes


# ---------- ديكور الورق (طبقة ثابتة على اللوحة) ----------

def _paste_shadow(base: Image.Image, layer: Image.Image, pos: tuple[int, int], shadow: float = 0.35,
                  blur: float = 7.0, offset: tuple[int, int] = (5, 7)) -> None:
    """يُلصق layer فوق base مع ظل ناعم."""
    if shadow > 0:
        alpha = layer.split()[-1]
        sh = Image.new("RGBA", layer.size, (0, 0, 0, 0))
        sh.paste((20, 16, 12, int(255 * shadow)), (0, 0), alpha)
        big = Image.new("RGBA", base.size, (0, 0, 0, 0))
        big.paste(sh, (pos[0] + offset[0], pos[1] + offset[1]), sh)
        big = big.filter(ImageFilter.GaussianBlur(blur))
        base.paste(Image.alpha_composite(base.crop((0, 0, base.width, base.height)).convert("RGBA"), big).convert("RGB"), (0, 0))
    base.paste(layer, pos, layer)


def _tape_layer(w: float, h: float, *, seed: int = 7) -> Image.Image:
    """شريط لاصق شبه شفاف (ورق مصفرّ) بحواف ممزقة."""
    rng = random.Random(seed)
    tw, th = int(w), int(h)
    im = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    base = (232 + rng.randint(-8, 8), 222 + rng.randint(-10, 8), 170 + rng.randint(-14, 12), 132)
    d.rectangle([0, 0, tw - 1, th - 1], fill=base)
    # خطوط ألياف
    for _ in range(max(3, tw // 40)):
        yy = rng.uniform(1, th - 2)
        d.line([0, yy, tw, yy + rng.uniform(-1, 1)], fill=(base[0] - 18, base[1] - 18, base[2] - 20, 60), width=1)
    # حافة ممزقة يمين/يسار
    for edge in (0, tw - 2):
        for y in range(0, th, 3):
            k = rng.randint(0, 2)
            d.rectangle([edge + (0 if edge == 0 else -k), y, edge + (k if edge == 0 else 0), y + 2],
                        fill=(0, 0, 0, 0))
    return im


def draw_paper_card(wb, rect, *, seed: int = 3, style: str = "photo", tilt: float = 1.4,
                    tape: bool = True, shadow: float = 0.35, border: int = 14,
                    card_color=(252, 250, 243), band_color=(249, 243, 224)) -> None:
    """بطاقة ورق خلف صورة/نص: بولارويد بظل وشريط لاصق (تُرسم مرة عند بدء العنصر).

    style: "photo" إطار بولارويد | "band" بطاقة بشريط علوي | "plain" بطاقة فقط.
    """
    x, y, w, h = [float(v) for v in rect]
    pad = border + 6
    cw, chh = int(w + pad * 2), int(h + pad * 2)
    card = Image.new("RGBA", (cw, chh), (0, 0, 0, 0))
    d = ImageDraw.Draw(card)
    d.rectangle([0, 0, cw - 1, chh - 1], fill=tuple(card_color) + (255,))
    d.rectangle([2, 2, cw - 3, chh - 3], outline=(214, 208, 194, 255), width=1)
    # مساحة الصورة (تُترك فارغة — الصورة تُرسم فوقها لاحقًا)
    d.rectangle([border, border, border + int(w) - 1, border + int(h) - 1], outline=(228, 222, 208, 255), width=1)
    if style == "band":
        d.rectangle([0, 0, cw - 1, int(max(18, border * 1.9))], fill=tuple(band_color) + (255,))
    if tilt:
        card = card.rotate(tilt, resample=Image.BICUBIC, expand=True, fillcolor=(0, 0, 0, 0))
    pos = (int(x - pad + (w + 2 * pad - card.width) / 2), int(y - pad + (h + 2 * pad - card.height) / 2))
    _paste_shadow(wb.rgb, card, pos, shadow=shadow, blur=7.5, offset=(6, 8))
    if tape:
        rng = random.Random(seed + 99)
        tw = int(cw * 0.30)
        for (ax, ay, ang) in ((x - pad * 0.2, y - pad * 0.6, -18 + rng.uniform(-6, 6)),
                              (x + w + pad * 0.2, y + h + pad * 0.2, 14 + rng.uniform(-6, 6))):
            tp = _tape_layer(tw, 26, seed=seed + int(ax))
            tp = tp.rotate(ang, resample=Image.BICUBIC, expand=True)
            wb.rgb.paste(tp, (int(ax - tp.width / 2), int(ay - tp.height / 2)), tp)


def draw_torn_strip(wb, rect, *, seed: int = 5, color=(250, 246, 233), tilt: float = 0.0,
                    shadow: float = 0.30, edge: float = 9.0) -> None:
    """شريط ورق ممزّق (لكولاج/بطاقات نص): حافّتان غير منتظمتين + ألياف."""
    x, y, w, h = [float(v) for v in rect]
    rng = random.Random(seed)
    pad = int(edge) + 6
    cw, chh = int(w + pad * 2), int(h + pad * 2)
    im = Image.new("RGBA", (cw, chh), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    pts_top = [(pad - 4, pad)]
    n = max(10, int(w / 26))
    for i in range(n + 1):
        pts_top.append((pad - 4 + (w + 8) * i / n, pad + rng.uniform(-edge, edge * 0.45)))
    pts_bot = []
    for i in range(n + 1):
        pts_bot.append((pad - 4 + (w + 8) * i / n, pad + h + rng.uniform(-edge * 0.45, edge)))
    poly = pts_top + [(pad + w + 4, pad + h + edge)] + list(reversed(pts_bot))
    d.polygon(poly, fill=tuple(color) + (255,))
    for _ in range(max(4, int(w / 50))):
        yy = rng.uniform(pad + 2, pad + h - 2)
        d.line([pad, yy, pad + w, yy + rng.uniform(-1, 1)], fill=(color[0] - 16, color[1] - 16, color[2] - 18, 40), width=1)
    if tilt:
        im = im.rotate(tilt, resample=Image.BICUBIC, expand=True, fillcolor=(0, 0, 0, 0))
    pos = (int(x - pad + (w + 2 * pad - im.width) / 2), int(y - pad + (h + 2 * pad - im.height) / 2))
    _paste_shadow(wb.rgb, im, pos, shadow=shadow, blur=5.5, offset=(4, 6))
