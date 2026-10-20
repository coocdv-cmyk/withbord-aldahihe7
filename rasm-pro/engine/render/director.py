"""المخرج: خطة المشاهد → فيديو (رسم تدريجي + كشف صور + كاميرا + ffmpeg).

- نص/أيقونات SVG: تُرسم بالحبر مسارًا مسارًا (إحساس اليد).
- صور فوتوغرافية: تُكشف تدريجيًا بقلم يتبع هيكل الصورة (نموذج mask path).
- الكاميرا تتبع العنصر الجاري رسمه بنعومة (مثل كاميرا الفيديو الاحترافية).
"""
from __future__ import annotations

import math
import time
from fractions import Fraction
from pathlib import Path

import numpy as np
from PIL import Image

from ..core.log import get_logger
from ..core.plan_time import scene_frame_bounds
from ..core.timebase import (
    FrameRate,
    SampleRate,
    TimebaseError,
    coerce_frame_rate,
    frame_rate_json,
    map_boundaries_to_frames,
)
from ..core.util import clamp, write_json
from ..strokes import find_font, raster_to_strokes, scan_svg, stroke_cache_path, text_to_strokes
from ..strokes.hand_timeline import HandTimeline
from ..strokes.model import Stroke, StrokeDoc
from .canvas import DocCursor, ImageReveal, Whiteboard, make_pen
from .camera import Viewport, crop_resize, fit_viewport, smooth_to
from .video import FFmpegWriter
from . import templates as T

log = get_logger("director")

DEFAULT_SPEED = 1200.0   # بكسل/ثانية على مقياس اللوحة المنطقية
MIN_DRAW_SEC = 0.4
INK = (34, 30, 26)


def _rgb(color, default=INK) -> tuple[int, int, int]:
    """يحوّل لون الخطة (#RRGGBB) إلى ثلاثية RGB لـPIL."""
    if not color:
        return default
    if isinstance(color, (tuple, list)) and len(color) >= 3:
        return tuple(int(c) for c in tuple(color)[:3])
    s = str(color).strip().lstrip("#")
    if len(s) == 3:
        s = "".join(ch * 2 for ch in s)
    try:
        return tuple(int(s[i : i + 2], 16) for i in (0, 2, 4))
    except Exception:
        return default


def clip_strokes(doc: StrokeDoc, rect) -> list[Stroke]:
    """يُحجّم مسارات مستند لتناسب مستطيلًا على اللوحة (مع حفظ النسبة والتوسيط)."""
    x, y, w, h = [float(v) for v in rect]
    sw, sh = float(doc.width or 1), float(doc.height or 1)
    s = min(w / sw, h / sh)
    ox = x + (w - sw * s) / 2.0
    oy = y + (h - sh * s) / 2.0
    out: list[Stroke] = []
    for st in doc.strokes:
        pts = [[ox + p[0] * s, oy + p[1] * s] for p in st.points]
        lengths = [l * s for l in st.lengths]
        prof = [max(0.7, b * s) for b in st.brush_profile] if st.brush_profile else None
        out.append(
            Stroke(points=pts, lengths=lengths, brush=max(0.7, st.brush * s), kind=st.kind,
                   color=st.color, brush_profile=prof, jumps=st.jumps, meta=st.meta)
        )
    return out


def strokes_bbox(strokes: list[Stroke]) -> tuple[float, float, float, float]:
    x0 = min(s.bbox[0] for s in strokes)
    y0 = min(s.bbox[1] for s in strokes)
    x1 = max(s.bbox[2] for s in strokes)
    y1 = max(s.bbox[3] for s in strokes)
    return (x0, y0, x1, y1)


def _sig(path) -> str:
    """بصمة ملف (وقت+حجم) لمفتاح الكاش."""
    try:
        st = Path(path).stat()
        return f"{int(st.st_mtime)}:{st.st_size}"
    except Exception:
        return "0:0"


# عدّادات الكاش (لتقرير الأداء: نسبة الإصابة الفعلية) — تكلفتها لا تُذكر.
CACHE_STATS = {"hit": 0, "miss": 0}


def _cached_doc(key: str, build) -> StrokeDoc:
    """يخزّن مسارات الأصل على القرص (أهم تحسين: لا نعيد التتبّع/التشكيل في كل رندر)."""
    p = stroke_cache_path(key)
    if p.exists():
        try:
            doc = StrokeDoc.load(p)
            CACHE_STATS["hit"] += 1
            return doc
        except Exception:
            CACHE_STATS["miss"] += 1
    else:
        CACHE_STATS["miss"] += 1
    doc = build()
    try:
        doc.save(p)
    except Exception as e:  # الكاش رفاهية — لا يُفشل الرندر
        log.warning("تعذّر حفظ كاش المسارات: %s", e)
    return doc


# نسخة أنبوب النص: يُرفع الرقم عند أي تغيير في Bidi/التشكيل/التخانة/الترتيب.
# بدون هذا، كاش القرص يعيد مسارات قديمة (حدث فعلًا: نص مقلوب من نسخة سابقة).
TEXT_PIPELINE_V = 6  # Phase 3.2: LTR خطي حقيقي + اتجاه الفقرة + أوزان الخط المتغيّرة


def load_doc(el: dict) -> StrokeDoc | None:
    t = el.get("type")
    if t == "text":
        font = find_font(el.get("font") or "arefruqaa")
        text = el.get("text", "")
        size = float(el.get("size") or 120)
        mode = el.get("mode", "skeleton")
        rtl_raw = el.get("rtl")
        rtl = None if rtl_raw is None else bool(rtl_raw)
        weight_raw = el.get("weight")
        weight = int(weight_raw) if weight_raw else None
        key = f"text|v{TEXT_PIPELINE_V}|{text}|{size}|{mode}|{rtl}|{weight}|{font}|{_sig(font)}"
        return _cached_doc(key, lambda: text_to_strokes(text, font, size, mode=mode, rtl=rtl, weight=weight))
    if t == "svg":
        path = el["asset"]
        return _cached_doc(f"svg|{path}|{_sig(path)}", lambda: scan_svg(path))
    return None


def _fatten(doc: StrokeDoc, k: float) -> StrokeDoc:
    """يوسّع الحبر (للكشف عن الصور: ممر قلم عريض بلا فراغات)."""
    for st in doc.strokes:
        st.brush = max(2.0, st.brush * k)
        if st.brush_profile:
            st.brush_profile = [max(1.6, p * k) for p in st.brush_profile]
    return doc


def _template_strokes(el: dict) -> list[Stroke]:
    """عناصر القوالب المرسومة باليد → مسارات (بنفس هندسة اللوحة)."""
    t = el.get("type")
    rect = [float(v) for v in (el.get("rect") or [0, 0, 800, 200])]
    color = el.get("color")
    if t == "highlight":
        return T.marker_band(rect, brush=el.get("brush"), seed=int(el.get("seed", 11)),
                             tilt=float(el.get("tilt", 0.02)), color=color)
    if t == "underline":
        return T.underline(rect, double=bool(el.get("double", False)), brush=float(el.get("brush", 4.5)),
                           seed=int(el.get("seed", 21)), offset=float(el.get("offset", 10.0)), color=color)
    if t == "flourish":
        return T.flourish(rect, brush=float(el.get("brush", 3.4)), seed=int(el.get("seed", 31)), color=color)
    if t == "arrow":
        p0 = el.get("from") or [rect[0], rect[1]]
        p1 = el.get("to") or [rect[0] + rect[2], rect[1] + rect[3]]
        return T.hand_arrow(p0, p1, brush=float(el.get("brush", 4.5)), seed=int(el.get("seed", 2)),
                            curve=float(el.get("curve", 0.22)), head=float(el.get("head", 34.0)))
    font = find_font(el.get("font") or "arefruqaa")
    if t == "timeline":
        return T.timeline_strokes(rect, el.get("events") or [], font_path=font,
                                  size=float(el.get("size", 70)), rtl=bool(el.get("rtl", True)),
                                  seed=int(el.get("seed", 41)), brush=float(el.get("brush", 5.0)), color=color)
    if t == "bars":
        return T.bars_strokes(rect, [float(v) for v in (el.get("values") or [])],
                              [str(s) for s in (el.get("labels") or [])], font_path=font,
                              size=float(el.get("size", 60)), seed=int(el.get("seed", 51)),
                              brush=float(el.get("brush", 5.0)), color=color, label_size=el.get("label_size"))
    return []


def _template_decor(el: dict):
    """ديكور ثابت (ورق/بطاقات) → دالة رسم على اللوحة، تُنفَّذ مرة واحدة."""
    t = el.get("type")
    rect = [float(v) for v in (el.get("rect") or [0, 0, 400, 300])]
    if t == "paper_card":
        style = el.get("style", "photo")
        tilt = float(el.get("tilt", 1.4))
        seed = int(el.get("seed", 3))
        tape = bool(el.get("tape", True))
        shadow = float(el.get("shadow", 0.35))
        border = int(el.get("border", 14))
        texture = el.get("texture")
        return lambda wb: T.draw_paper_card(wb, rect, seed=seed, style=style, tilt=tilt, tape=tape,
                                            shadow=shadow, border=border, texture=texture)
    if t in ("texture", "background"):
        path = el.get("asset") or el.get("texture")
        if not path:
            return None
        opacity = float(el.get("opacity", 1.0))
        fit = str(el.get("fit", "cover"))
        return lambda wb: T.draw_texture(wb, rect, path, opacity=opacity, fit=fit)
    if t == "torn_strip":
        seed = int(el.get("seed", 5))
        tilt = float(el.get("tilt", 0.0))
        col = el.get("paper_color") or (250, 246, 233)
        col = tuple(int(c) for c in col) if isinstance(col, (list, tuple)) else (250, 246, 233)
        return lambda wb: T.draw_torn_strip(wb, rect, seed=seed, color=col, tilt=tilt)
    return None


class Director:
    def __init__(
        self,
        plan: dict,
        *,
        canvas: tuple[int, int] = (2560, 1440),
        out_size: tuple[int, int] = (1280, 720),
        fps: FrameRate | int | float | str | dict | None = None,
        speed: float = DEFAULT_SPEED,
        crf: int = 19,
        preset: str = "fast",
        ink=INK,
    ):
        self.plan = plan
        self.canvas = (int(canvas[0]), int(canvas[1]))
        self.out_size = (int(out_size[0]), int(out_size[1]))
        # قاعدة زمن واحدة: لو الخطة تحمل fps، فالرندر يجب أن يطابقها.
        # لا نسمح بتمدد صامت (30 → 24 كان يطيل المشهد 25%).
        plan_rate = coerce_frame_rate(plan["fps"]) if plan.get("fps") is not None else None
        if fps is None:
            self.fps_rate = plan_rate or FrameRate(24)
        else:
            self.fps_rate = coerce_frame_rate(fps)
            if plan_rate is not None and self.fps_rate.value != plan_rate.value:
                raise TimebaseError(
                    f"تعارض معدل الإطارات: الخطة {plan_rate} والرندر {self.fps_rate}. "
                    "أعد بناء الخطة بنفس المعدل أو استخدم تحويلًا صريحًا."
                )
        self.fps = self.fps_rate.fps
        self.speed = float(speed)
        self.crf = int(crf)
        self.preset = preset
        self.ink = tuple(ink)
        # القلم: صورة مربعة طرفها في مركزها — تُدار حول الطرف بلا قصّ
        size = max(160, int(self.out_size[1] * 0.72))
        self.pen = make_pen(size)
        self.pen_tip = (self.pen.width / 2.0, self.pen.height / 2.0)
        self.pen_angle = 90.0
        self.pen_prev: tuple[float, float] | None = None
        self.pen_rot = None
        self.pen_rot_angle = None
        # أحداث القلم (للصوت): تُجمع أثناء الرندر وتُكتب بجانب الفيديو
        self.sfx_events: list[dict] = []

    # ---------- تجهيز ----------
    def _prepare_scene(self, scene: dict, planned_seconds: float | None = None) -> tuple[list[dict], float]:
        items: list[dict] = []
        t = float(scene.get("start_pause", 0.35))
        for el in scene.get("elements", []):
            rect = el.get("rect") or [0, 0, 800, 600]
            etype = el.get("type")
            gap = float(el.get("gap", 0.22))
            if etype == "image":
                path = el["asset"]
                try:
                    img = Image.open(path).convert("RGB")
                except Exception as e:
                    log.warning("تخطّي صورة غير مقروءة %s: %s", path, e)
                    continue
                doc = _cached_doc(
                    f"raster|{path}|{_sig(path)}|{int(el.get('trace_size', 900))}|{bool(el.get('rtl', False))}",
                    lambda: raster_to_strokes(np.asarray(img), max_size=int(el.get("trace_size", 900)), rtl=bool(el.get("rtl", False))),
                )
                if not doc.strokes:
                    continue
                strokes = clip_strokes(_fatten(doc, 2.8), rect)
                # صندوق عرض الصورة: نفس تحجيم المسارات (حفظ النسبة + توسيط)
                s = min(float(rect[2]) / float(doc.width or 1), float(rect[3]) / float(doc.height or 1))
                bw, bh = float(doc.width or 1) * s, float(doc.height or 1) * s
                box = (float(rect[0]) + (float(rect[2]) - bw) / 2.0, float(rect[1]) + (float(rect[3]) - bh) / 2.0, bw, bh)
                reveal = ImageReveal(img, strokes, rect, img_box=box)
                # كشف الصورة: مدة مضبوطة (لا الزمن الطبيعي للمسح — كثافة المسارات
                # في الصور الفوتوغرافية تجعله دقائق). قابلة للتجاوز لكل عنصر.
                dur = max(1.5, float(el.get("reveal_time", 6.0)))
                items.append({"kind": "reveal", "obj": reveal, "start": t, "dur": dur, "bbox": strokes_bbox(strokes), "el": el, "gap": gap})
                t += dur + gap
            elif etype in ("text", "svg"):
                doc = load_doc(el)
                if not doc or not doc.strokes:
                    continue
                strokes = clip_strokes(doc, rect)
                words = None
                try:
                    words = (doc.stats or {}).get("words")
                except Exception:
                    words = None
                tl = HandTimeline(strokes, words=words)
                dur = max(MIN_DRAW_SEC, tl.wall_for_speed(self.speed))
                items.append({"kind": "stroke", "obj": tl, "start": t, "dur": dur, "bbox": strokes_bbox(strokes),
                              "el": el, "gap": gap, "nat": tl.natural, "events": True, "_prev": 0.0})
                t += dur + gap
            elif etype in ("highlight", "underline", "flourish", "arrow", "timeline", "bars"):
                strokes = _template_strokes(el)
                if not strokes:
                    continue
                speed = self.speed * float(el.get("speed", 1.0))
                tl = HandTimeline(strokes)
                dur = max(MIN_DRAW_SEC, tl.wall_for_speed(speed))
                items.append({"kind": "stroke", "obj": tl, "start": t, "dur": dur, "bbox": strokes_bbox(strokes),
                              "el": el, "gap": gap, "nat": tl.natural,
                              "events": bool(el.get("events", True)), "_prev": 0.0})
                t += dur + gap
            elif etype in ("paper_card", "torn_strip", "texture", "background"):
                fn = _template_decor(el)
                if fn is None:
                    continue
                x, y, w, h = [float(v) for v in rect]
                pad = 40.0
                items.append({"kind": "paint_once", "fn": fn, "start": t, "dur": 0.001,
                              "bbox": (x - pad, y - pad, x + w + pad, y + h + pad), "el": el,
                              "gap": float(el.get("gap", 0.08))})
                t += float(el.get("reveal_time", 0.12)) + float(el.get("gap", 0.08))
        natural_end = max((it["start"] + it["dur"] for it in items), default=0.0)
        self._fit_timings(items, planned_seconds)
        return items, natural_end

    def _fit_timings(self, items: list[dict], planned_seconds: float | None) -> list[dict]:
        """يضبط توقيت العناصر داخل مدة المشهد المخططة (بلا مدد منفجرة).

        القاعدة: كل العناصر تنتهي قبل نهاية المشهد بـ0.6ث، مع حد أدنى 0.45ث للعنصر.
        """
        if not items:
            return items
        # The first item's start already contains the scene's start pause.
        start = float(items[0].get("start", 0.0))
        planned = float(planned_seconds or 0.0)
        natural_end = max(it["start"] + it["dur"] for it in items)
        if planned <= 0 or natural_end <= planned:
            return items
        available = max(len(items) * MIN_DRAW_SEC, planned - start - 0.6)
        weights = [max(0.2, it["dur"]) for it in items]
        total_w = sum(weights)
        gaps = sum(it.get("gap", 0.22) for it in items)
        avail = max(len(items) * MIN_DRAW_SEC, available - gaps)
        t = start
        for it, w in zip(items, weights):
            dur = max(MIN_DRAW_SEC, avail * (w / total_w))
            it["dur"] = dur
            it["start"] = t
            t += dur + it.get("gap", 0.22)
        return items

    def scene_bounds(self, *, scene_range: tuple[int, int] | None = None,
                     max_seconds: float | None = None) -> list[dict]:
        """حدود المشاهد بالإطارات المطلقة — مصدر واحد للرندر والتقرير."""
        return scene_frame_bounds(
            self.plan,
            max_seconds=max_seconds,
            scene_range=scene_range,
        )

    def _draw_pen(self, frame, active: dict | None, cam):
        """يرسم القلم عند نقطة الرسم الحالية (بزاوية تتبع اتجاه الحركة، بنعومة)."""
        if active is None:
            return frame
        obj = active.get("obj")
        tip = obj.tip() if hasattr(obj, "tip") else None
        if tip is None:
            return frame
        sx = self.out_size[0] / cam.w
        sy = self.out_size[1] / cam.h
        px = (tip[0] - cam.x) * sx
        py = (tip[1] - cam.y) * sy
        if self.pen_prev is not None:
            dx = px - self.pen_prev[0]
            dy = py - self.pen_prev[1]
            if abs(dx) + abs(dy) > 0.6:
                tgt = 90.0 - math.degrees(math.atan2(dy, dx))
                diff = ((tgt - self.pen_angle + 180.0) % 360.0) - 180.0
                self.pen_angle += diff * 0.18
        self.pen_prev = (px, py)
        if self.pen_rot is None or self.pen_rot_angle is None or abs(self.pen_angle - self.pen_rot_angle) >= 2.0:
            self.pen_rot = self.pen.rotate(self.pen_angle, resample=Image.BICUBIC, center=self.pen_tip)
            self.pen_rot_angle = self.pen_angle
        frame.paste(self.pen_rot, (int(round(px - self.pen_tip[0])), int(round(py - self.pen_tip[1]))), self.pen_rot)
        return frame

    # ---------- الرندر ----------
    def render(self, out_path: str | Path, *, audio: str | Path | None = None, max_seconds: float | None = None,
               scene_range: tuple[int, int] | None = None, on_progress=None) -> dict:
        cw, ch = self.canvas
        aspect = self.out_size[0] / self.out_size[1]
        self.sfx_events = []
        bounds = self.scene_bounds(scene_range=scene_range, max_seconds=max_seconds)
        if not bounds:
            raise TimebaseError("لا توجد مشاهد قابلة للرندر بعد تطبيق النطاق/الحد الزمني")
        expected_frames = sum(int(b["frames"]) for b in bounds)
        writer = FFmpegWriter(
            out_path,
            self.out_size,
            fps=self.fps_rate,
            crf=self.crf,
            preset=self.preset,
            audio=audio,
            expected_frames=expected_frames,
        )
        frames_total = 0
        scene_report: list[dict] = []
        t0 = time.time()
        audio_cfg = self.plan.get("audio") or {}
        sample_rate = int(audio_cfg.get("sample_rate") or 0)
        output_start_frame = int(bounds[0]["start_frame"])

        for bound in bounds:
            idx = int(bound["index"])
            scene = bound["scene"]
            frames = int(bound["frames"])
            source_frames = int(bound.get("source_frames") or frames)
            planned_seconds = float(self.fps_rate.time_of_frames(source_frames))
            # لوحة نضيفة لكل مشهد: لا تراكم عناصر فوق بعضها
            wb = Whiteboard(cw, ch, ink=self.ink)
            cam = Viewport(0.0, 0.0, float(cw), float(ch))
            items, natural_end = self._prepare_scene(scene, planned_seconds)
            overflow = natural_end > planned_seconds + 1e-9
            scene_report.append({
                "id": scene.get("id"),
                "index": idx,
                "frames": frames,
                "seconds": round(float(self.fps_rate.time_of_frames(frames)), 6),
                "start": round(frames_total / self.fps, 6),
                "start_frame": int(bound["start_frame"]),
                "end_frame": int(bound["end_frame"]),
                "source_frames": source_frames,
                "source_seconds": round(planned_seconds, 6),
                "overflow": bool(overflow),
                "natural_seconds": round(float(natural_end), 6),
            })
            log.info(
                "مشهد %d: %d عنصر · %.3fث · %d إطار%s",
                idx, len(items), planned_seconds, frames, " ⚠ overflow" if overflow else "",
            )
            scene_base_frame = int(bound["start_frame"])
            scene_project_start = self.fps_rate.time_of_frames(scene_base_frame)
            scene_output_base = frames_total
            scene_output_start = self.fps_rate.time_of_frames(scene_output_base)
            for f in range(frames):
                local_time = self.fps_rate.time_of_frames(f)
                t = float(local_time)
                active = None
                for it in items:
                    if t < it["start"]:
                        continue
                    prog = clamp((t - it["start"]) / it["dur"], 0.0, 1.0) if it["dur"] > 0 else 1.0
                    if it["kind"] == "reveal":
                        it["obj"].advance(prog)
                        it["obj"].blit(wb)
                    elif it["kind"] == "paint_once":
                        if not it.get("_done"):
                            it["fn"](wb)
                            it["_done"] = True
                        continue
                    else:
                        wb.paint(it["obj"].advance(prog), ink=_rgb(it["el"].get("color")))
                        if it.get("events"):
                            nat = float(it.get("nat") or 1.0)
                            prev = float(it.get("_prev", 0.0))
                            if prog > prev:
                                for ev in it["obj"].events_between(prev * nat, prog * nat):
                                    offset = Fraction(str(it["start"])) + (
                                        Fraction(str(ev.t)) / Fraction(str(nat))
                                    ) * Fraction(str(it["dur"]))
                                    event_abs = scene_project_start + offset
                                    out_abs = scene_output_start + offset
                                    frame_no = self.fps_rate.frame_of_time(event_abs, mode="round")
                                    out_frame_no = self.fps_rate.frame_of_time(out_abs, mode="round")
                                    sample_no = None
                                    if sample_rate > 0:
                                        sample_no = int(round(event_abs * sample_rate))
                                    self.sfx_events.append({
                                        # Absolute project clock (contract).
                                        "frame": frame_no,
                                        "sample": sample_no,
                                        "t": round(float(event_abs), 6),
                                        # Output-relative clock (used by the SFX mix).
                                        "output_frame": out_frame_no,
                                        "output_t": round(float(out_abs), 6),
                                        "kind": ev.kind,
                                        "x": round(ev.x, 1),
                                        "y": round(ev.y, 1),
                                        "stroke": ev.stroke,
                                        "scene": scene.get("id"),
                                        "el": it["el"].get("id"),
                                    })
                                it["_prev"] = prog
                    if prog < 1.0 and active is None:
                        active = it
                if active:
                    x0, y0, x1, y1 = active["bbox"]
                    zoom_w = clamp((x1 - x0) * 2.6, cw * 0.46, float(cw))
                    target = fit_viewport((x0 + x1) / 2, (y0 + y1) / 2, aspect, zoom_w=zoom_w, canvas_w=cw, canvas_h=ch)
                else:
                    target = Viewport(0.0, 0.0, float(cw), float(ch))
                cam = smooth_to(cam, target, 0.07)
                frame = crop_resize(wb.rgb, cam, self.out_size)
                frame = self._draw_pen(frame, active, cam)
                writer.write(frame)
                frames_total += 1
            if on_progress:
                on_progress(idx, frames_total)

        writer.close()
        if frames_total != expected_frames:
            raise TimebaseError(
                f"عدد الإطارات المكتوب ({frames_total}) لا يطابق حدود الزمن ({expected_frames})"
            )
        exact_seconds = self.fps_rate.time_of_frames(frames_total)
        sfx_path = None
        if self.sfx_events:
            try:
                sfx_path = str(Path(str(out_path)).with_suffix(".sfx.json"))
                write_json(
                    sfx_path,
                    {
                        "fps": self.fps_rate.fps,
                        "fps_rate": frame_rate_json(self.fps_rate),
                        "frames": frames_total,
                        "duration_sec_exact": str(exact_seconds),
                        "canvas": list(self.canvas),
                        "scenes": scene_report,
                        "events": self.sfx_events,
                    },
                )
                log.info("أحداث القلم للصوت: %d حدث → %s", len(self.sfx_events), Path(sfx_path).name)
            except Exception as e:
                log.warning("تعذّر حفظ أحداث الصوت: %s", e)
                sfx_path = None
        return {
            "frames": frames_total,
            "seconds": round(float(exact_seconds), 6),
            "duration_sec_exact": str(exact_seconds),
            "fps": frame_rate_json(self.fps_rate),
            "fps_value": self.fps_rate.fps,
            "out": str(out_path),
            "render_seconds": round(time.time() - t0, 1),
            "scenes": scene_report,
            "expected_frames": expected_frames,
            "narration_frames": expected_frames,
            "drift_frames": frames_total - expected_frames,
            "output_start_frame": output_start_frame,
            "sfx": sfx_path,
            "pen_events": len(self.sfx_events),
            "overflow_scenes": [s["id"] for s in scene_report if s.get("overflow")],
        }
