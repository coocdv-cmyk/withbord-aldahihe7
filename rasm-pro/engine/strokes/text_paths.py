"""النص → مسارات رسم حقيقية (تشكيل عربي صحيح + كتابة متصلة مرتّبة موثّقة).

- التشكيل: HarfBuzz (uharfbuzz) — ربط الحروف، اللام-ألف، RTL، الحركات.
- التخطيط: تقسيم السطر إلى كلمات (tokens)، تشكيل كل كلمة بمقاطع اتجاهها (bidi)،
  ثم وضع الكلمات من اليمين لليسار. حدود الكلمات حقيقية وتُستخدم لإيقاع الرسم.
- الوحدة الأساسية الآن **الكلمة لا الحرف**: تُركّب أقنعة الحروف في قناع واحد
  للكلمة ثم يُستخرج الهيكل مرة واحدة — فالحبر يتصل بين الحروف المترابطة كما في
  الكتابة الحقيقية، ورفع القلم يحدث فقط حيث يوجد فصل حقيقي (نقاط الإعجام،
  وصلات تحدث في الكتابة اليدوية).
- ترتيب الرسم: يبدأ من أقصى اليمين ويمشي يسارًا (المسار البياني في hand_order):
  البداية من نهاية السنّ اليمنى، رفع القلم عند الانحشار بلا خطوط عبر الفراغ،
  والنقاط تُنقَر بعد الجسم.
- الأرقام تُرسم من اليسار لليمين (اتجاه LTR) كما تُكتب.
- عند تعذّر المعالجة: احتياط آمن = محيط الحرف (لا نعرض تتبّعًا مغلوطًا).
- الناتج: StrokeDoc + stats.words (حدود الكلمات لإيقاع الزمن) لخط الزمن اليدوي.

إصلاحات Phase 3.1 المثبتة معمليًا:
  1) تخفيف Guo-Hall وحده (Zhang-Suen القديم كان يفتّت المنحنيات إلى شرطات:
     حلقة 5px → 53 مكوّنًا).
  2) ترتيب كتابة يمين→يسار لكل مقطع RTL (كان يأتي من HarfBuzz يسار→يمين).
  3) رفع القلم عند كل قفزة حقيقية في التتبّع (كانت تُرسم خطوط عبر الفراغ).
  4) إزاحة مكوّنات الحرف صحيحة (كانت مكوّنات الجسم تُزاح بأصل الحرف كاملًا).
"""
from __future__ import annotations

import math
import re
from pathlib import Path

import numpy as np

from ..core.paths import FONTS
from .hand_order import order_mask_paths
from .mask_path import points_to_lengths
from .model import Stroke, StrokeDoc
from .thinning import thin

try:
    import uharfbuzz as hb  # type: ignore
except Exception:  # pragma: no cover
    hb = None

try:
    import cv2  # type: ignore
except Exception:  # pragma: no cover
    cv2 = None

try:
    from scipy import ndimage as ndi  # type: ignore
except Exception:  # pragma: no cover
    ndi = None

from fontTools.misc.transform import Transform
from fontTools.pens.recordingPen import DecomposingRecordingPen, RecordingPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont


# ---------- اكتشاف الخطوط ----------

def list_fonts() -> dict[str, list[Path]]:
    """كل الخطوط المتاحة مجمّعة بالعائلة."""
    out: dict[str, list[Path]] = {}
    if not FONTS.exists():
        return out
    for fam_dir in sorted(FONTS.iterdir()):
        if fam_dir.is_dir():
            files = sorted(fam_dir.glob("*.ttf"))
            if files:
                out[fam_dir.name] = files
    return out


def find_font(name_part: str, prefer_bold: bool = False) -> Path:
    """يبحث عن خط بالاسم (جزء منه). يرجع أول مطابقة."""
    name_part = name_part.lower().replace(" ", "")
    fonts = list_fonts()
    for slug, files in fonts.items():
        if name_part in slug.lower():
            if prefer_bold:
                for f in files:
                    if "bold" in f.name.lower():
                        return f
            for f in files:
                if "italic" not in f.name.lower() and "[" not in f.name:  # مثبّت مفضّل
                    return f
            return files[0]
    raise FileNotFoundError(f"لم يُعثر على خط يطابق: {name_part}")


# ---------- تسطيح منحنيات fontTools ----------

def _cubic_points(p0, c1, c2, p1, steps: int) -> list[list[float]]:
    pts = []
    for i in range(1, steps + 1):
        t = i / steps
        mt = 1 - t
        x = mt**3 * p0[0] + 3 * mt**2 * t * c1[0] + 3 * mt * t**2 * c2[0] + t**3 * p1[0]
        y = mt**3 * p0[1] + 3 * mt**2 * t * c1[1] + 3 * mt * t**2 * c2[1] + t**3 * p1[1]
        pts.append([x, y])
    return pts


def _quad_points(p0, c1, p1, steps: int) -> list[list[float]]:
    pts = []
    for i in range(1, steps + 1):
        t = i / steps
        mt = 1 - t
        x = mt**2 * p0[0] + 2 * mt * t * c1[0] + t**2 * p1[0]
        y = mt**2 * p0[1] + 2 * mt * t * c1[1] + t**2 * p1[1]
        pts.append([x, y])
    return pts


def _steps_for(p0, p1, scale_est=1.0) -> int:
    d = math.dist(p0, p1) * scale_est
    return int(max(3, min(48, d / 2.0)))


def _contours_from_recording(rec: RecordingPen) -> list[tuple[list[list[float]], bool]]:
    """يحوّل تسجيل fontTools إلى كنتورات مسطّحة [(نقاط, مغلق؟)]."""
    contours: list[tuple[list[list[float]], bool]] = []
    cur: list[list[float]] = []
    closed = False

    def finish():
        nonlocal cur, closed
        if len(cur) >= 2:
            contours.append((cur, closed))
        cur = []
        closed = False

    for op, args in rec.value:
        if op == "moveTo":
            finish()
            cur = [list(args[0])]
        elif op == "lineTo":
            cur.append(list(args[0]))
        elif op == "qCurveTo":
            pts = [list(a) for a in args]
            # TrueType: عدة نقاط تحكّم → نقاط وسيطة ضمنية
            if pts[-1] is None:
                pts = pts[:-1]
                # منحنى مغلق بالكامل: أضف البداية كنهاية
                pts = pts + [pts[0]]
            offs = pts[:-1]
            on = pts[-1]
            prev = cur[-1]
            if len(offs) == 1:
                c = offs[0]
                cur += _quad_points(prev, c, on, _steps_for(prev, on))
            else:
                # توسيع TrueType: قمم وسيطة = منتصف كل نقطتي تحكم متتاليتين
                start = prev
                for i, c in enumerate(offs):
                    if i < len(offs) - 1:
                        nxt_c = offs[i + 1]
                        mid = [(c[0] + nxt_c[0]) / 2, (c[1] + nxt_c[1]) / 2]
                    else:
                        mid = on
                    cur += _quad_points(start, c, mid, _steps_for(start, mid))
                    start = mid
                if cur[-1] != on:
                    cur.append(list(on))
        elif op == "curveTo":
            c1, c2, p1 = [list(a) for a in args]
            prev = cur[-1]
            cur += _cubic_points(prev, c1, c2, p1, _steps_for(prev, p1))
        elif op == "closePath":
            closed = True
            finish()
        elif op == "endPath":
            finish()
    finish()
    return contours


# ---------- rasterizing contours (individual/hole) ----------

def _fill_contours_evenodd(contours: list[tuple[list[list[float]], bool]], w: int, h: int, offset=(0.0, 0.0)) -> np.ndarray:
    """يرستر الكنتورات بقاعدة individual/hole (استبعاد الثقوب)."""
    mask = np.zeros((h, w), dtype=np.uint8)
    if cv2 is None or not contours:
        return mask.astype(bool)
    polys = []
    for pts, _closed in contours:
        arr = np.array([[int(round(x + offset[0])), int(round(y + offset[1]))] for x, y in pts], dtype=np.int32)
        if len(arr) >= 3:
            polys.append(arr)
    # ترتيب بالمساحة تنازليًا
    areas = [abs(cv2.contourArea(p)) for p in polys]
    order = sorted(range(len(polys)), key=lambda i: -areas[i])
    for idx in order:
        arr = polys[idx]
        # هل هذه حفرة؟ نقطة اختبار داخل عدد فردي من الكنتورات الأكبر
        test_pt = (float(arr[0][0]), float(arr[0][1]))
        inside = 0
        for jdx in order:
            if jdx == idx or areas[jdx] <= areas[idx]:
                continue
            if cv2.pointPolygonTest(polys[jdx], test_pt, False) > 0:
                inside += 1
        val = 0 if inside % 2 == 1 else 1
        cv2.fillPoly(mask, [arr], val)
    return mask.astype(bool)


# ---------- Bidi: تقسيم السطر إلى مقاطع اتجاه (RTL/LTR) ----------
#
# HarfBuzz لا يطبّق خوارزمية bidi: تشكيل سطر كامل باتجاه RTL يقلب الأرقام
# («1914» ← «4191») ويخلط اللاتيني داخل العربي. لذلك نفصل السطر إلى مقاطع
# منطقية بحسب نوع المحرف، ونشكّل كل مقطع باتجاهه، ثم نضع المقاطع بصريًا
# من اليمين لليسار في الفقرة العربية (تقريب آمن ومقصود من UAX#9 يكفي
# للعربية مع أرقام/أسماء أجنبية/نسب/أقواس/تواريخ).

_ARABIC_RANGES = ((0x0600, 0x06FF), (0x0750, 0x077F), (0x08A0, 0x08FF), (0xFB50, 0xFDFF), (0xFE70, 0xFEFF))
_MIRROR = str.maketrans("()[]{}<>", ")(][}{><")

_PUNCT_END = re.compile(r"[.،!؟:…]$")


def _char_class(ch: str) -> str:
    """R عربي · L لاتيني · EN أرقام غربية · AN أرقام عربية · N محايد."""
    cp = ord(ch)
    if 0x064B <= cp <= 0x065F or cp == 0x0670:  # تشكيل: يتبع ما حوله
        return "N"
    if 0x0660 <= cp <= 0x0669 or 0x06F0 <= cp <= 0x06F9:
        return "AN"
    if 0x30 <= cp <= 0x39:
        return "EN"
    if any(a <= cp <= b for a, b in _ARABIC_RANGES):
        return "R"
    if ch.isalpha():
        return "L"
    return "N"


def _resolve_neutrals(classes: list[str], base_rtl: bool) -> list[str]:
    """محايد بين قويّين متجانسين يأخذ اتجاههما، وإلا فاتجاه الفقرة."""
    out = list(classes)
    n = len(classes)
    strong = ("R", "L", "EN", "AN")
    for i, c in enumerate(classes):
        if c != "N":
            continue
        left = next((classes[j] for j in range(i - 1, -1, -1) if classes[j] in strong), None)
        right = next((classes[j] for j in range(i + 1, n) if classes[j] in strong), None)
        ld = "R" if left == "R" else ("L" if left else None)
        rd = "R" if right == "R" else ("L" if right else None)
        if ld is not None and ld == rd:
            out[i] = "R" if ld == "R" else "L"
        elif ld is None and rd is not None:
            out[i] = rd
        elif rd is None and ld is not None:
            out[i] = ld
        else:
            out[i] = "R" if base_rtl else "L"
    return out


def _bidi_runs(text: str, base_rtl: bool) -> list[tuple[str, str]]:
    """مقاطع (نص، اتجاه) بالترتيب المنطقي: rtl أو ltr."""
    classes = _resolve_neutrals([_char_class(ch) for ch in text], base_rtl)
    runs: list[tuple[list[str], str]] = []
    for ch, c in zip(text, classes):
        d = "rtl" if c == "R" else "ltr"
        if runs and runs[-1][1] == d:
            runs[-1][0].append(ch)
        else:
            runs.append(([ch], d))
    return [("".join(chars), d) for chars, d in runs]


class _FontShaper:
    """مُشكّل خط واحد: يخزّن face/font مرة واحدة ويشكّل المقاطع باتجاهاتها."""

    def __init__(self, font_path: Path):
        if hb is None:
            raise RuntimeError("uharfbuzz غير مثبّت")
        self.font_path = Path(font_path)
        self.blob = hb.Blob.from_file_path(str(self.font_path))
        self.face = hb.Face(self.blob)
        self.font = hb.Font(self.face)
        self.upem = self.face.upem or 1000
        self.font.scale = (self.upem, self.upem)

    def _shape_run(self, text: str, size: float, direction: str, *, mirror: bool) -> tuple[list[dict], float]:
        if mirror:
            text = text.translate(_MIRROR)
        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        buf.direction = direction
        hb.shape(self.font, buf, {"kern": True, "liga": True, "calt": True})
        s = size / self.upem
        glyphs: list[dict] = []
        pen = 0.0
        for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
            glyphs.append(
                {
                    "gid": info.codepoint,
                    "cluster": info.cluster,
                    "x": pen + pos.x_offset * s,
                    "y": pos.y_offset * s,
                    "advance": pos.x_advance * s,
                    "rtl": direction == "rtl",
                }
            )
            pen += pos.x_advance * s
        return glyphs, pen

    def shape_line(self, text: str, size: float, force_rtl: bool | None = None) -> tuple[list[dict], float, bool]:
        """يعيد (الحروف بمواضعها المطلقة، عرض السطر، اتجاه الفقرة). [توافق خلفي]"""
        has_rtl = any(_char_class(ch) == "R" for ch in text)
        if force_rtl is None:
            base_rtl = has_rtl  # أول حرف قوي عمليًا
        else:
            base_rtl = bool(force_rtl) and has_rtl
        if not has_rtl and not any(_char_class(ch) == "L" for ch in text):
            base_rtl = bool(force_rtl)  # سطر أرقام/رموز بحت: نتبع الطلب
        runs = _bidi_runs(text, base_rtl)
        shaped: list[tuple[list[dict], float]] = [
            self._shape_run(rt, size, d, mirror=(d == "rtl")) for rt, d in runs
        ]
        total = sum(w for _, w in shaped)
        glyphs: list[dict] = []
        if base_rtl:
            cursor = total
            for g, w in shaped:
                left = cursor - w
                for gg in g:
                    gg["x"] = left + gg["x"]
                    glyphs.append(gg)
                cursor = left
        else:
            cursor = 0.0
            for g, w in shaped:
                for gg in g:
                    gg["x"] = cursor + gg["x"]
                    glyphs.append(gg)
                cursor += w
        return glyphs, total, base_rtl


def _shape_line(text: str, font_path: Path, size: float, force_rtl: bool | None = None):
    """توافق خلفي للأدوات: (حروف، عرض، rtl، upem، scale)."""
    sh = _FontShaper(Path(font_path))
    glyphs, width, base_rtl = sh.shape_line(text, size, force_rtl=force_rtl)
    return glyphs, width, base_rtl, sh.upem, size / sh.upem


# ---------- هندسة الحرف: قناع محلي مخزّن مؤقتًا (بدون تخانة) ----------

_GLYPH_MEMO: dict[tuple, dict | None] = {}
_RS = 2  # دقة القناع (بكسل لكل وحدة مستند)

# عرض القلم: سقف أعلى من الوسيط (شبكة أمان من الانتفاخ عند الوصلات) وأرضية للشعرية.
# المعايرة أظهرت أن السقف لا يقيّد فوق 2.4 (الملمح = مسافة-التحول الحقيقية)،
# و2.6 محافظ + يحفظ تباين الرقعة. (2.6 بضمان 2.4× الوسيط، أرض 1.0; لم تُوثَّق كمعايرة مستقلة.)
PROFILE_CAP_FACTOR = 2.6
PROFILE_FLOOR = 0.55


def _smooth(vals: list[float], window: int = 2) -> list[float]:
    """تمهيد متحرك صغير لسماكة القلم (يمنع نبض العرض)."""
    if len(vals) <= 2 or window <= 0:
        return vals
    out = []
    for i in range(len(vals)):
        a = max(0, i - window)
        b = min(len(vals), i + window + 1)
        seg = vals[a:b]
        out.append(sum(seg) / len(seg))
    return out


def _label8(mask: np.ndarray) -> list[dict]:
    """مكوّنات متصلة 8-اتجاه: [{y0,x0,sub,area}]."""
    if ndi is not None:
        lab, n = ndi.label(mask.astype(np.uint8), structure=np.ones((3, 3), dtype=np.uint8))
        comps: list[dict] = []
        for i in range(1, int(n) + 1):
            ys, xs = np.nonzero(lab == i)
            if len(ys) == 0:
                continue
            y0, y1 = int(ys.min()), int(ys.max())
            x0, x1 = int(xs.min()), int(xs.max())
            sub = np.zeros((y1 - y0 + 1, x1 - x0 + 1), dtype=bool)
            sub[ys - y0, xs - x0] = True
            comps.append({"y0": y0, "x0": x0, "sub": sub, "area": int(len(ys))})
        return comps
    # احتياطي: المكوّن كله واحد (نادرًا ما نحتاجه)
    ys, xs = np.nonzero(mask)
    if len(ys) == 0:
        return []
    y0, y1 = int(ys.min()), int(ys.max())
    x0, x1 = int(xs.min()), int(xs.max())
    sub = mask[y0:y1 + 1, x0:x1 + 1].copy()
    return [{"y0": y0, "x0": x0, "sub": sub, "area": int(len(ys))}]


def _glyph_raster(font_path: Path, glyph_set, glyph_order, gid: int, size: float, s: float):
    """قناع حرف واحدة بإحداثيات محلية (مخزّن مؤقتًا لكل خط/حجم/gid).

    الاتفاقية: بكسل القناع (mx,my) ↔ محلي (x0 + mx/RS, y0 + my/RS)،
    ثم التوضّع النهائي: (g.x + x0 + mx/RS, (baseline - g.y) + y0 + my/RS).
    """
    key = (str(font_path), round(float(size), 4), int(gid))
    if key in _GLYPH_MEMO:
        return _GLYPH_MEMO[key]

    name = glyph_order[gid] if 0 <= gid < len(glyph_order) else None
    result: dict | None = None
    if name is not None:
        rec = DecomposingRecordingPen(glyph_set)
        transform = Transform(s, 0, 0, -s, 0.0, 0.0)  # محلي: ثم نُزيح عند التجميع
        glyph_set[name].draw(TransformPen(rec, transform))
        contours = _contours_from_recording(rec)
        if contours:
            xs = [p[0] for c, _ in contours for p in c]
            ys = [p[1] for c, _ in contours for p in c]
            if xs:
                gx0, gy0 = min(xs) - 3.0, min(ys) - 3.0
                gx1, gy1 = max(xs) + 3.0, max(ys) + 3.0
                w = int(math.ceil((gx1 - gx0))) * _RS
                h = int(math.ceil((gy1 - gy0))) * _RS
                if 2 <= w * h <= 16_000_000:
                    scaled = [([[(x - gx0) * _RS, (y - gy0) * _RS] for x, y in c], cl) for c, cl in contours]
                    mask = _fill_contours_evenodd(scaled, w, h)
                    if mask.any():
                        result = {"mask": mask, "x0": gx0, "y0": gy0, "contours": contours}
    _GLYPH_MEMO[key] = result
    return result


def _process_mask(mask: np.ndarray, size: float, rtl: bool, ox: float, oy: float, rs: int = _RS) -> dict:
    """هيكل قناع (حرف أو كلمة كاملة) → مسارات كتابة مرتّبة بإحداثيات المستند.

    يعيد {"points": [...{x,y,moveTo}], "profiles": [...], "dots": n, "bodies": n}.
    """
    points: list[dict] = []
    profiles: list[float] = []
    dot_count = 0
    body_count = 0

    dist = None
    if cv2 is not None:
        dist = cv2.distanceTransform(mask.astype(np.uint8), cv2.DIST_L2, 3)

    comps = _label8(mask)
    bodies: list[dict] = []
    dots: list[dict] = []
    for cp in comps:
        sub = cp["sub"]
        bh, bw = sub.shape
        max_local = max(bw, bh) / rs
        area_local = cp["area"] / (rs * rs)
        fill_ratio = cp["area"] / float(bw * bh) if bw and bh else 0.0
        is_dot = (
            max_local <= 0.24 * size
            and area_local <= 0.012 * size * size
            and fill_ratio >= 0.50
        )
        (dots if is_dot else bodies).append(cp)

    def cx_of(cp: dict) -> float:
        return cp["x0"] + cp["sub"].shape[1] / 2.0

    def cy_of(cp: dict) -> float:
        return cp["y0"] + cp["sub"].shape[0] / 2.0

    if rtl:
        bodies.sort(key=lambda cp: -cx_of(cp))          # أيمن أولًا
        dots.sort(key=lambda cp: (-cx_of(cp), cy_of(cp)))  # أيمن ثم أعلى
    else:
        bodies.sort(key=lambda cp: cx_of(cp))           # أيسر أولًا
        dots.sort(key=lambda cp: (cx_of(cp), cy_of(cp)))

    for cp in bodies:
        sub = cp["sub"]
        th, _iters = thin(sub)
        if not th.any():
            continue
        pts = order_mask_paths(th, rtl=rtl)
        if not pts:
            continue
        prof: list[float] = []
        for pp in pts:
            ym = min(max(int(pp["y"]) + cp["y0"], 0), mask.shape[0] - 1)
            xm = min(max(int(pp["x"]) + cp["x0"], 0), mask.shape[1] - 1)
            if dist is not None:
                prof.append(float(dist[ym, xm]) * 0.98 / rs)
            else:
                prof.append(max(0.7, min(sub.shape) / (2.0 * rs)))
        if not prof:
            continue
        prof = _smooth(prof, 2)
        med = float(np.median(prof))
        cap = max(med * PROFILE_CAP_FACTOR, 1.0)
        prof = [max(PROFILE_FLOOR, min(v, cap)) for v in prof]
        for pp in pts:
            x_doc = ox + (pp["x"] + cp["x0"]) / rs
            y_doc = oy + (pp["y"] + cp["y0"]) / rs
            points.append({"x": x_doc, "y": y_doc, "moveTo": bool(pp.get("moveTo"))})
        profiles.extend(prof)
        body_count += 1

    for cp in dots:
        ys2, xs2 = np.nonzero(cp["sub"])
        cy = oy + (float(ys2.mean()) + cp["y0"]) / rs
        cx = ox + (float(xs2.mean()) + cp["x0"]) / rs
        r = max(1.0, 0.5 * max(cp["sub"].shape) / rs)
        points.append({"x": cx, "y": cy, "moveTo": True})
        points.append({"x": cx + 0.02, "y": cy, "moveTo": False})
        profiles.extend([r, r])
        dot_count += 1

    return {"points": points, "profiles": profiles, "dots": dot_count, "bodies": body_count}


# ---------- تخطيط السطر: كلمات تُوضع يمين→يسار ----------

def _split_tokens(line: str) -> list[tuple[str, int]]:
    """يعيد [(كلمة، عدد المسافات قبلها)] بالترتيب المنطقي."""
    parts = re.split(r"(\s+)", line)
    tokens: list[tuple[str, int]] = []
    pending = 0
    for part in parts:
        if not part:
            continue
        if part.isspace():
            pending += len(part)
        else:
            tokens.append((part, pending))
            pending = 0
    return tokens


def _space_advance(tt: TTFont, upem: int, size: float) -> float:
    """عرض المسافة من الخط نفسه (hmtx) — أساس تباعد كلمات صحيح."""
    try:
        cmap = tt.getBestCmap()
        gname = cmap.get(0x20)
        if gname is not None:
            return float(tt["hmtx"][gname][0]) / upem * size
    except Exception:
        pass
    return size * 0.26


def text_to_strokes(
    text: str,
    font_path: str | Path,
    size: float = 64,
    *,
    mode: str = "skeleton",
    rtl: bool | None = None,
    line_spacing: float = 1.45,
    color: str | None = None,
    asset: str | None = None,
) -> StrokeDoc:
    """النص → StrokeDoc (متجهي حقيقي) بأسلوب كتابة متصلة يمين→يسار للعربية."""
    font_path = Path(font_path)
    tt = TTFont(str(font_path), fontNumber=0, lazy=True)
    upem = tt["head"].unitsPerEm
    ascent = getattr(tt["hhea"], "ascent", int(upem * 0.8))
    descent = abs(getattr(tt["hhea"], "descent", int(upem * 0.2)))
    glyph_set = tt.getGlyphSet()
    glyph_order = tt.getGlyphOrder()

    lines = text.split("\n") if text else [""]
    line_h = size * line_spacing
    ascent_px = ascent / upem * size
    s = size / upem
    space_w = _space_advance(tt, upem, size)
    shaper = _FontShaper(font_path)

    all_strokes: list[Stroke] = []
    words: list[dict] = []
    fallback_tokens = 0
    fallback_glyphs = 0
    dot_total = 0
    max_w = 0.0

    for li, line in enumerate(lines):
        if not line.strip():
            continue
        baseline = ascent_px + li * line_h

        has_rtl = any(_char_class(ch) == "R" for ch in line)
        if rtl is None:
            base_rtl = has_rtl
        else:
            base_rtl = bool(rtl) and has_rtl
        if not has_rtl and not any(_char_class(ch) == "L" for ch in line):
            base_rtl = bool(rtl)

        cursor = 0.0  # حدّ اليمين للسطر (كل السطور محاذاة يمين)
        for tok, spaces_before in _split_tokens(line):
            tok_rtl = any(_char_class(ch) == "R" for ch in tok)
            runs: list[tuple[str, str, list[dict], float]] = []
            for rt, d in _bidi_runs(tok, base_rtl):
                gs, wd = shaper._shape_run(rt, size, d, mirror=(d == "rtl"))
                runs.append((rt, d, gs, wd))
            tok_w = sum(wd for _, _, _, wd in runs)
            tok_left = cursor - tok_w

            if tok_rtl:
                # المقاطع تُوضع يمين→يسار داخل الكلمة (الأول منطقيًا أيمن بصريًا)
                rcursor = cursor
                for _rt, _d, gs, wd in runs:
                    run_left = rcursor - wd
                    for gg in gs:
                        gg["x"] = run_left + gg["x"]
                    rcursor = run_left
            else:
                rcursor = tok_left
                for _rt, _d, gs, wd in runs:
                    for gg in gs:
                        gg["x"] = rcursor + gg["x"]
                    rcursor += wd

            # ---------- تجميع قناع الكلمة كوحدة واحدة ----------
            placements: list[dict] = []
            for _rt, d, gs, _wd in runs:
                glyph_iter = list(reversed(gs)) if d == "rtl" else list(gs)
                for g in glyph_iter:
                    gid = g["gid"]
                    raster = _glyph_raster(font_path, glyph_set, glyph_order, gid, size, s)
                    if raster is None:
                        continue
                    placements.append(
                        {
                            "mask": raster["mask"],
                            "x0": g["x"] + raster["x0"],
                            "y0": (baseline - g["y"]) + raster["y0"],
                            "name": glyph_order[gid] if 0 <= gid < len(glyph_order) else None,
                            "contours": raster["contours"],
                            "g": g,
                        }
                    )

            if mode == "outline":
                # الوضع الطباعي: محيط الحروف فقط (مرجع للتحقق + كشف تدريجي)
                for gi, pl in enumerate(placements):
                    base_x = pl["g"]["x"]
                    base_y = baseline - pl["g"]["y"]
                    for cpts, closed in pl["contours"]:
                        pcl = [[round(x + base_x, 2), round(y + base_y, 2)] for x, y in cpts]
                        if closed:
                            pcl.append(list(pcl[0]))
                        if len(pcl) < 2:
                            continue
                        lengths2: list[float] = []
                        total2 = 0.0
                        for i2, p2 in enumerate(pcl):
                            if i2:
                                total2 += math.dist(p2, pcl[i2 - 1])
                            lengths2.append(total2)
                        all_strokes.append(
                            Stroke(points=pcl, lengths=lengths2, brush=max(size / 26.0, 1.2),
                                   kind="glyph", color=color,
                                   meta={"glyph": pl["name"], "gi": gi, "fill": [pcl], "rtl": tok_rtl})
                        )
                words.append(
                    {
                        "start": len(all_strokes) - len(placements),
                        "end": len(all_strokes),
                        "rtl": tok_rtl,
                        "punct": bool(_PUNCT_END.search(tok)),
                        "text": tok,
                    }
                )
                cursor = tok_left - spaces_before * space_w
                continue

            word_start = len(all_strokes)
            token_fallback = False
            if placements:
                # كانفاس الاتحاد
                x_min = min(int(math.floor(pl["x0"] * _RS)) for pl in placements) - 4
                y_min = min(int(math.floor(pl["y0"] * _RS)) for pl in placements) - 4
                x_max = max(int(math.ceil((pl["x0"] * _RS) + pl["mask"].shape[1])) for pl in placements) + 4
                y_max = max(int(math.ceil((pl["y0"] * _RS) + pl["mask"].shape[0])) for pl in placements) + 4
                canvas = np.zeros((y_max - y_min, x_max - x_min), dtype=bool)
                for pl in placements:
                    m = pl["mask"]
                    ox_i = int(round(pl["x0"] * _RS)) - x_min
                    oy_i = int(round(pl["y0"] * _RS)) - y_min
                    canvas[oy_i:oy_i + m.shape[0], ox_i:ox_i + m.shape[1]] |= m
                origin_x = x_min / _RS
                origin_y = y_min / _RS

                if tok_rtl:
                    res = _process_mask(canvas, size=size, rtl=True, ox=origin_x, oy=origin_y)
                else:
                    res = _process_mask(canvas, size=size, rtl=False, ox=origin_x, oy=origin_y)

                if res["points"]:
                    pts_dicts = res["points"]
                    coords, lengths, jumps = points_to_lengths(pts_dicts)
                    prof = res["profiles"]
                    brush = float(np.median(prof)) if prof else max(size / 30.0, 1.1)
                    dot_total += int(res["dots"])
                    all_strokes.append(
                        Stroke(
                            points=coords,
                            lengths=lengths,
                            brush=max(brush, 0.8),
                            kind="glyph",
                            color=color,
                            brush_profile=prof if prof else None,
                            jumps=jumps or None,
                            meta={
                                "token": tok,
                                "rtl": tok_rtl,
                                "dots": int(res["dots"]),
                                "bodies": int(res["bodies"]),
                            },
                        )
                    )
                else:
                    token_fallback = True
            else:
                token_fallback = True

            if token_fallback:
                # احتياط آمن: رسم محيط الحروف بدل مسار مغلوط (وضع طباعي)
                fallback_tokens += 1
                for pl in placements:
                    fallback_glyphs += 1
                    base_x = pl["g"]["x"]
                    base_y = baseline - pl["g"]["y"]
                    for cpts, closed in pl["contours"]:
                        pcl = [[round(x + base_x, 2), round(y + base_y, 2)] for x, y in cpts]
                        if closed:
                            pcl.append(list(pcl[0]))
                        if len(pcl) < 2:
                            continue
                        lengths2: list[float] = []
                        total = 0.0
                        for i2, p2 in enumerate(pcl):
                            if i2:
                                total += math.dist(p2, pcl[i2 - 1])
                            lengths2.append(total)
                        all_strokes.append(
                            Stroke(points=pcl, lengths=lengths2, brush=max(size / 40.0, 0.9),
                                   kind="glyph", color=color,
                                   meta={"token": tok, "fallback": "outline"})
                        )

            words.append(
                {
                    "start": word_start,
                    "end": len(all_strokes),
                    "rtl": tok_rtl,
                    "punct": bool(_PUNCT_END.search(tok)),
                    "text": tok,
                }
            )
            cursor = tok_left - spaces_before * space_w
        max_w = max(max_w, -cursor)

    # تطبيع الإحداثيات: أصل المستند عند (0,0) وأبعاد مشدودة على الحبر
    width = 0.0
    height = 0.0
    norm_offset = [0.0, 0.0]
    if all_strokes:
        xs2 = [p[0] for st in all_strokes for p in st.points]
        ys2 = [p[1] for st in all_strokes for p in st.points]
        min_x, min_y = min(xs2), min(ys2)
        max_x, max_y = max(xs2), max(ys2)
        norm_offset = [round(min_x, 4), round(min_y, 4)]
        if abs(min_x) > 1e-9 or abs(min_y) > 1e-9:
            for st in all_strokes:
                st.points = [[p[0] - min_x, p[1] - min_y] for p in st.points]
                fill = st.meta.get("fill")
                if fill:
                    st.meta["fill"] = [[[p[0] - min_x, p[1] - min_y] for p in c] for c in fill]
                rings = st.meta.get("rings")
                if rings:
                    st.meta["rings"] = [[[p[0] - min_x, p[1] - min_y] for p in c] for c in rings]
        width = float(max_x - min_x)
        height = float(max_y - min_y)
    else:
        width = float(max_w)
        height = float(ascent_px + descent / upem * size + (len(lines) - 1) * line_h)

    doc = StrokeDoc(
        asset=asset or f"text:{text[:24]}",
        source="text",
        width=width,
        height=height,
        strokes=all_strokes,
        stats={
            "glyph_strokes": len(all_strokes),
            "total_length": sum(s2.total_length for s2 in all_strokes),
            "mode": mode,
            "size": size,
            "font": font_path.name,
            "words": words,
            "dots": dot_total,
            "fallback_glyphs": fallback_glyphs,
            "fallback_tokens": fallback_tokens,
            "norm_offset": norm_offset,
            "pipeline": "hand-union-1" if mode == "skeleton" else "outline",
        },
    )
    return doc
