"""لوحة الوايت بورد: ورق + حبر + كشف تدريجي للصور.

- Whiteboard: صورة RGB كبيرة يُرسم عليها الحبر مباشرة (تراكمي).
- StrokeCursor: يمشي على مسار ويرسم الأجزاء الجديدة فقط (بلا إعادة رسم).
- ImageReveal: صورة تُكشف تدريجيًا بقناع يتراكم بنقاط القلم (نموذج mask path في VideoScribe).
"""
from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from ..strokes.hand_timeline import HandTimeline
from ..strokes.model import Stroke


def make_paper(w: int, h: int, *, color=(248, 244, 234), noise: float = 5.0, vignette: float = 0.05, seed: int = 7) -> Image.Image:
    """ورق واقعي: لون دافئ + حبيبات خفيفة + تظليل أطراف (بلا أي أصول خارجية)."""
    rng = np.random.default_rng(seed)
    base = np.empty((h, w, 3), dtype=np.float32)
    base[:, :] = color
    if noise > 0:
        base += rng.normal(0.0, noise, (h, w, 1)).astype(np.float32)
    if vignette > 0:
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        cx, cy = (w - 1) / 2, (h - 1) / 2
        r = np.sqrt(((xx - cx) / cx) ** 2 + ((yy - cy) / cy) ** 2)
        base *= (1.0 - vignette * np.clip(r, 0, 1.5) ** 2)[..., None]
    return Image.fromarray(np.clip(base, 0, 255).astype(np.uint8), "RGB")


def make_pen(size: int = 340, width: int | None = None) -> Image.Image:
    """قلم حبر أنيق (RGBA): كرة السن في **مركز** الصورة تمامًا — يُدار حول الطرف بلا قصّ.

    الطول ≤ 0.30×الحجم من السن، فيبقى داخل المربع عند أي زاوية دوران.
    """
    ss = 4
    S = int(size) * ss
    cx = cy = S / 2.0
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))

    pw = S * 0.050            # عرض الجسم
    grip_w = pw * 0.94
    ball_r = max(2.0, pw * 0.17)
    pen_len = S * 0.300       # السن → أعلى الجسم

    neck_y = cy - pw * 1.7
    grip_top = neck_y - pw * 1.9
    band_top = grip_top - pw * 0.34
    top_y = cy - pen_len

    # ظل ناعم تحت القلم
    sh = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle(
        (cx - pw / 2 + pw * 0.30, top_y + pw * 0.35, cx + pw / 2 + pw * 0.55, neck_y + pw * 0.5),
        radius=pw * 0.55, fill=(24, 22, 20, 70),
    )
    img = Image.alpha_composite(img, sh.filter(ImageFilter.GaussianBlur(pw * 0.45)))
    d = ImageDraw.Draw(img)

    body = (48, 52, 62, 255)
    grip = (66, 70, 82, 255)
    metal = (196, 200, 210, 255)
    nib = (36, 38, 44, 255)

    # الجسم + القبضة + حلقات الإمساك + الحلقة المعدنية
    d.rounded_rectangle((cx - pw / 2, top_y, cx + pw / 2, band_top + 2), radius=pw * 0.5, fill=body)
    d.rounded_rectangle((cx - grip_w / 2, grip_top, cx + grip_w / 2, neck_y + 2), radius=grip_w * 0.35, fill=grip)
    for k in range(3):
        y = grip_top + pw * 0.42 + k * pw * 0.42
        d.line((cx - grip_w * 0.36, y, cx + grip_w * 0.36, y), fill=(30, 32, 38, 160), width=max(1, int(pw * 0.07)))
    d.rounded_rectangle((cx - pw * 0.56, band_top, cx + pw * 0.56, grip_top + 1), radius=pw * 0.16, fill=metal)
    d.line((cx - pw * 0.5, (band_top + grip_top) / 2, cx + pw * 0.5, (band_top + grip_top) / 2),
           fill=(120, 124, 134, 180), width=max(1, int(pw * 0.05)))
    # المشبك
    d.rounded_rectangle((cx - pw * 0.62, top_y + pw * 0.45, cx - pw * 0.34, band_top + pw * 0.2),
                        radius=pw * 0.13, fill=metal)
    # السن + كرة الطرف عند المركز تمامًا
    d.polygon([(cx - grip_w * 0.42, neck_y + 1), (cx + grip_w * 0.42, neck_y + 1),
               (cx + ball_r * 0.9, cy - ball_r), (cx - ball_r * 0.9, cy - ball_r)], fill=nib)
    d.ellipse((cx - ball_r, cy - ball_r, cx + ball_r, cy + ball_r), fill=(14, 14, 16, 255))
    d.ellipse((cx - ball_r * 0.45, cy - ball_r * 0.55, cx + ball_r * 0.05, cy - ball_r * 0.1), fill=(230, 230, 235, 140))

    # لمعة يمين وظل يسار على الجسم
    hl = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    hd = ImageDraw.Draw(hl)
    hd.rounded_rectangle((cx + pw * 0.16, top_y + pw * 0.3, cx + pw * 0.42, band_top - pw * 0.15),
                         radius=pw * 0.12, fill=(255, 255, 255, 60))
    hd.rounded_rectangle((cx - pw * 0.46, top_y + pw * 0.3, cx - pw * 0.28, band_top - pw * 0.15),
                         radius=pw * 0.1, fill=(0, 0, 0, 70))
    img = Image.alpha_composite(img, hl)

    return img.resize((int(size), int(size)), Image.LANCZOS)


class StrokeCursor:
    """حالة رسم مسار واحد: يعطي الأجزاء الجديدة فقط كل تقدّم."""

    __slots__ = ("stroke", "pts", "lens", "jumps", "seg_i", "seg_t", "done", "total", "tip_xy")

    def __init__(self, stroke: Stroke):
        self.stroke = stroke
        self.pts = stroke.points
        self.lens = stroke.lengths
        self.jumps = set(stroke.jumps or [])
        self.seg_i = 0
        self.seg_t = 0.0
        self.total = stroke.total_length
        self.done = len(self.pts) < 2
        self.tip_xy: tuple[float, float] | None = None

    def advance(self, upto: float) -> list[tuple[float, float, float, float, float]]:
        """(x0,y0,x1,y1,radius) للأجزاء الجديدة حتى الطول المطلوب."""
        out: list[tuple[float, float, float, float, float]] = []
        pts, lens = self.pts, self.lens
        n = len(pts)
        while self.seg_i < n - 1:
            i = self.seg_i
            if (i + 1) in self.jumps:  # رفع القلم: لا رسم بين النقطتين
                self.seg_i += 1
                self.seg_t = 0.0
                continue
            seg_start, seg_end = lens[i], lens[i + 1]
            if upto <= seg_start:
                break
            t0 = self.seg_t
            t1 = 1.0 if upto >= seg_end else (upto - seg_start) / max(seg_end - seg_start, 1e-9)
            if t1 <= t0:
                break
            x0 = pts[i][0] + (pts[i + 1][0] - pts[i][0]) * t0
            y0 = pts[i][1] + (pts[i + 1][1] - pts[i][1]) * t0
            x1 = pts[i][0] + (pts[i + 1][0] - pts[i][0]) * t1
            y1 = pts[i][1] + (pts[i + 1][1] - pts[i][1]) * t1
            prof = self.stroke.brush_profile
            if prof and i + 1 < len(prof):
                r = max(0.6, 0.5 * (prof[i] + prof[i + 1]))
            else:
                r = max(0.6, self.stroke.brush)
            out.append((x0, y0, x1, y1, r))
            self.tip_xy = (x1, y1)
            if upto >= seg_end:
                self.seg_i += 1
                self.seg_t = 0.0
            else:
                self.seg_t = t1
                break
        self.done = self.seg_i >= n - 1
        return out


class Whiteboard:
    """لوحة الحبر: رسم تراكمي سريع + تجميع المقاطع في خطوط متصلة."""

    def __init__(self, w: int, h: int, *, paper: Image.Image | None = None, ink=(34, 30, 26), seed: int = 7):
        self.w, self.h = int(w), int(h)
        self.paper = paper or make_paper(self.w, self.h, seed=seed)
        self.rgb = self.paper.copy()
        self.ink = tuple(ink)
        self._draw = ImageDraw.Draw(self.rgb)

    # ---------- الرسم ----------
    def paint(self, segs: list[tuple[float, float, float, float, float]], ink=None) -> None:
        """يرسم مقاطع متتابعة كخطوط متصلة — **دون** وصل المقاطع المنفصلة.

        فاصل حقيقي (رفع قلم/انتقال) = نهاية مقطع لا تساوي بداية التالي:
        نُنهي الخط الحالي ونبدأ خطًا جديدًا (لا خطوط قطرية عبر الفراغ — عيب مثبت).
        """
        if not segs:
            return
        color = tuple(ink) if ink else self.ink
        line: list[tuple[float, float]] = [(segs[0][0], segs[0][1])]
        radii: list[float] = [segs[0][4]]
        prev_end = (segs[0][0], segs[0][1])
        prev_tail: tuple[float, float, float] | None = None  # (x, y, r) لآخر مقطع مرسوم
        for (x0, y0, x1, y1, r) in segs:
            if abs(x0 - prev_end[0]) + abs(y0 - prev_end[1]) > 0.75:
                self._flush(line, radii, color)
                # فجوة قصيرة = وصل/تفرّع (ليس رفع قلم): قرص وصل يمنع الشقوق الرقيقة
                if prev_tail is not None:
                    gap = math.hypot(x0 - prev_tail[0], y0 - prev_tail[1])
                    if gap <= 3.0 * max(prev_tail[2], r, 1.0):
                        jr = max(prev_tail[2], r) * 1.15
                        self._draw.ellipse((x0 - jr, y0 - jr, x0 + jr, y0 + jr), fill=color)
                line = []
                radii = []
            elif radii and abs(r - radii[-1]) > 0.35 * max(radii[-1], 1.0):
                self._flush(line, radii, color)
                line = []
                radii = []
            if not line:
                line.append((x0, y0))
                radii.append(r)
            line.append((x1, y1))
            radii.append(r)
            prev_end = (x1, y1)
            prev_tail = (x1, y1, r)
        self._flush(line, radii, color)

    def _flush(self, line: list[tuple[float, float]], radii: list[float], color) -> None:
        if len(line) < 2:
            if line and radii:
                x, y = line[0]
                r = radii[0]
                self._draw.ellipse((x - r, y - r, x + r, y + r), fill=color)
            return
        # شريط متغيّر العرض: حدود يسار/يمين ثم تعبئة واحدة — لا شقوق وصل بين خطوط متعددة
        n = min(len(line), len(radii))
        pts, rs = line[:n], [max(0.5, r) for r in radii[:n]]
        left: list[tuple[float, float]] = []
        right: list[tuple[float, float]] = []
        for i in range(n):
            x, y = pts[i]
            r = rs[i]
            if i == 0:
                dx, dy = pts[1][0] - x, pts[1][1] - y
            elif i == n - 1:
                dx, dy = x - pts[-2][0], y - pts[-2][1]
            else:
                dx, dy = pts[i + 1][0] - pts[i - 1][0], pts[i + 1][1] - pts[i - 1][1]
            ln = math.hypot(dx, dy) or 1.0
            nx, ny = -dy / ln, dx / ln
            left.append((x + nx * r, y + ny * r))
            right.append((x - nx * r, y - ny * r))
        self._draw.polygon(left + right[::-1], fill=color)
        for p, rr in ((pts[0], rs[0]), (pts[-1], rs[-1])):
            self._draw.ellipse((p[0] - rr, p[1] - rr, p[0] + rr, p[1] + rr), fill=color)

    def dot(self, x: float, y: float, r: float, ink=None) -> None:
        color = tuple(ink) if ink else self.ink
        self._draw.ellipse((x - r, y - r, x + r, y + r), fill=color)

    def stroke_outline(self, stroke: Stroke, ink=None) -> None:
        """يرسم مسارًا كاملًا دفعة واحدة (للأشكال الجاهزة)."""
        cur = StrokeCursor(stroke)
        self.paint(cur.advance(stroke.total_length + 1.0), ink=ink)


class DocCursor:
    """يمشي على مستند كامل (عدة مسارات) بميزانية طول واحدة — إيقاع رسم متصل."""

    def __init__(self, strokes: list[Stroke]):
        self.cursors = [StrokeCursor(s) for s in strokes]
        self.lengths = [c.total for c in self.cursors]
        self.total = sum(self.lengths) or 1.0

    def advance(self, fraction: float) -> list[tuple[float, float, float, float, float]]:
        budget = max(0.0, min(1.0, fraction)) * self.total
        out: list[tuple[float, float, float, float, float]] = []
        used = 0.0
        for cur, length in zip(self.cursors, self.lengths):
            if used >= budget:
                break
            local = min(length, budget - used)
            used += length
            out.extend(cur.advance(local))
        return out

    @property
    def done(self) -> bool:
        return all(c.done for c in self.cursors)

    def tip(self) -> tuple[float, float] | None:
        """نقطة القلم الحالية (آخر نقطة رُسمت)."""
        for cur in reversed(self.cursors):
            if cur.tip_xy is not None:
                return cur.tip_xy
        return None


class ImageReveal:
    """كشف صورة تدريجيًا عبر قناع يتراكم بحركة القلم (نموذج mask path).

    الملاحظة: المسارات مُسبقًا مُقاسة على فضاء اللوحة (نفس وحدة المستطيل الهدف).
    """

    def __init__(self, image: Image.Image, strokes: list[Stroke], rect: tuple[float, float, float, float],
                 img_box: tuple[float, float, float, float] | None = None):
        self.src = image.convert("RGB")
        x, y, w, h = rect
        self.rect = (float(x), float(y), float(w), float(h))
        # صندوق الصورة = نفس تحجيم مسارات القلم (حفظ النسبة + توسيط) — وإلا وُضع
        # القناع في مكان والصورة في مكان آخر (خِطأ كشف مثبت مع الصور غير المطابقة للنسبة).
        if img_box is not None:
            bx, by, bw, bh = img_box
            self.origin = (int(round(bx)), int(round(by)))
            self.size = (max(2, int(round(bw))), max(2, int(round(bh))))
        else:
            self.size = (max(2, int(round(w))), max(2, int(round(h))))
            self.origin = (int(round(x)), int(round(y)))
        # خط زمن الكتابة: انتقالات قلم حقيقية بين المسارات (بلا خطوط عبر الفراغ)
        self.timeline = HandTimeline(strokes, ease=False, travel_pps=4000.0)
        self.mask = Image.new("L", self.size, 0)
        self.mdraw = ImageDraw.Draw(self.mask)
        self.scaled_img: Image.Image | None = None
        self.done = False

    def advance(self, fraction: float) -> None:
        segs = self.timeline.advance(fraction)
        if not segs:
            return
        ox, oy = self.origin
        for (x0, y0, x1, y1, r) in segs:
            wpx = max(1, int(round(2 * r)))
            self.mdraw.line((x0 - ox, y0 - oy, x1 - ox, y1 - oy), fill=255, width=wpx, joint="curve")
            self.mdraw.ellipse((x1 - ox - r, y1 - oy - r, x1 - ox + r, y1 - oy + r), fill=255)
        self.done = float(fraction) >= 1.0 or self.timeline.done

    def tip(self) -> tuple[float, float] | None:
        return self.timeline.tip()

    def blit(self, wb: Whiteboard) -> None:
        if self.scaled_img is None:
            self.scaled_img = self.src.resize(self.size, Image.LANCZOS)
        wb.rgb.paste(self.scaled_img, self.origin, self.mask)
