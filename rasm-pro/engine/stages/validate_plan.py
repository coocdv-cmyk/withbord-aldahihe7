"""Deterministic plan validation.

This is intentionally stricter than the renderer: it catches mistakes before a
long render starts, while keeping recoverable style issues as warnings.
"""
from __future__ import annotations

import math
from fractions import Fraction
from pathlib import Path
from typing import Any

from ..core import arabic
from ..core.plan_time import scene_frame_bounds
from ..core.timebase import TimebaseError, coerce_frame_rate, map_boundaries_to_frames, SampleRate
from ..strokes import find_font

ELEMENT_TYPES = {
    "text", "svg", "image", "highlight", "underline", "flourish", "arrow",
    "timeline", "bars", "paper_card", "torn_strip", "texture", "background",
}
FONT_MODES = {"skeleton", "outline"}
CARD_STYLES = {"photo", "band", "plain"}


def _is_num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(float(v))


def _rect(value: Any) -> tuple[float, float, float, float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    if not all(_is_num(v) for v in value):
        return None
    x, y, w, h = (float(v) for v in value)
    if w <= 0 or h <= 0:
        return None
    return x, y, w, h


def _resolve_asset(value: Any, project_dir: Path | None) -> Path | None:
    if not value or not isinstance(value, (str, Path)):
        return None
    p = Path(value)
    if p.is_absolute():
        return p if p.exists() else None
    roots = []
    if project_dir:
        roots.append(Path(project_dir))
    roots += [Path.cwd(), Path(__file__).resolve().parents[2]]
    for root in roots:
        q = root / p
        if q.exists():
            return q
    return None


def validate_plan(plan: Any, *, project_dir: str | Path | None = None,
                  check_assets: bool = True) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    pd = Path(project_dir) if project_dir else None

    if not isinstance(plan, dict):
        return {"ok": False, "errors": ["plan is not an object"], "warnings": [],
                "stats": {"scenes": 0, "elements": 0, "duration": 0.0}}

    canvas = plan.get("canvas")
    cw, ch = 2560, 1440
    if canvas is not None:
        if not isinstance(canvas, (list, tuple)) or len(canvas) != 2 or not all(_is_num(v) and int(v) > 0 for v in canvas):
            errors.append("canvas must be [width, height] with positive numbers")
        else:
            cw, ch = int(canvas[0]), int(canvas[1])

    raw_fps = plan.get("fps", 24)
    rate = None
    try:
        rate = coerce_frame_rate(raw_fps)
    except TimebaseError:
        errors.append("fps must be a positive number or rational {num, den}")

    scenes = plan.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        errors.append("scenes must be a non-empty list")
        scenes = []

    seen_scene_ids: set[str] = set()
    total_elements = 0
    total_duration = 0.0
    scene_timing: list[dict] = []
    for si, scene in enumerate(scenes, 1):
        where = f"scene {si}"
        if not isinstance(scene, dict):
            errors.append(f"{where}: scene must be an object")
            continue
        sid = scene.get("id")
        if sid is None:
            errors.append(f"{where}: missing id")
        else:
            key = str(sid)
            if key in seen_scene_ids:
                errors.append(f"{where}: duplicate scene id {sid!r}")
            seen_scene_ids.add(key)
            where = f"scene {sid}"

        duration = scene.get("duration")
        if duration is not None:
            if not _is_num(duration) or float(duration) <= 0:
                errors.append(f"{where}: duration must be positive")
            else:
                total_duration += float(duration)
        df = scene.get("duration_frames")
        if df is not None and (
            not _is_num(df) or float(df) <= 0 or not float(df).is_integer()
        ):
            errors.append(f"{where}: duration_frames must be a positive integer")

        sf = scene.get("start_frame")
        ef = scene.get("end_frame")
        if (sf is None) != (ef is None):
            errors.append(f"{where}: start_frame and end_frame must be provided together")
        elif sf is not None:
            if not _is_num(sf) or not float(sf).is_integer() or float(sf) < 0:
                errors.append(f"{where}: start_frame must be a non-negative integer")
            if not _is_num(ef) or not float(ef).is_integer():
                errors.append(f"{where}: end_frame must be an integer")
            if _is_num(sf) and _is_num(ef) and float(ef) <= float(sf):
                errors.append(f"{where}: end_frame must be greater than start_frame")
            if df is not None and _is_num(df) and _is_num(sf) and _is_num(ef) and int(df) != int(ef) - int(sf):
                errors.append(f"{where}: duration_frames must equal end_frame - start_frame")
            if rate is not None and duration is not None and _is_num(duration):
                expected = rate.frames_for_duration(Fraction(str(duration)), mode="round")
                if _is_num(df) and abs(expected - int(df)) > 1:
                    warnings.append(
                        f"{where}: duration_frames ({int(df)}) differs from the rounded duration ({expected})"
                    )

        ss = scene.get("start_sample")
        es = scene.get("end_sample")
        if (ss is None) != (es is None):
            errors.append(f"{where}: start_sample and end_sample must be provided together")
        elif ss is not None:
            if not _is_num(ss) or not float(ss).is_integer() or float(ss) < 0:
                errors.append(f"{where}: start_sample must be a non-negative integer")
            if not _is_num(es) or not float(es).is_integer():
                errors.append(f"{where}: end_sample must be an integer")
            if _is_num(ss) and _is_num(es) and float(es) <= float(ss):
                errors.append(f"{where}: end_sample must be greater than start_sample")
            if _is_num(ss) and _is_num(es) and df is not None and _is_num(df) and rate is not None:
                audio = plan.get("audio") or {}
                sr = int(audio.get("sample_rate") or 0)
                if sr > 0:
                    mapped = map_boundaries_to_frames(
                        [int(ss), int(es)], SampleRate(sr), rate, mode="round"
                    )
                    if mapped[1] - mapped[0] != int(df):
                        errors.append(
                            f"{where}: duration_frames ({int(df)}) does not match sample span "
                            f"({mapped[1] - mapped[0]})"
                        )

        scene_timing.append({"id": sid, "start_frame": sf, "end_frame": ef,
                             "start_sample": ss, "end_sample": es, "duration_frames": df})

        pause = scene.get("start_pause")
        if pause is not None and (not _is_num(pause) or float(pause) < 0):
            errors.append(f"{where}: start_pause must be >= 0")

        elements = scene.get("elements")
        if not isinstance(elements, list):
            errors.append(f"{where}: elements must be a list")
            continue
        if not elements:
            warnings.append(f"{where}: no elements")
        for ei, el in enumerate(elements, 1):
            ewhere = f"{where} element {ei}"
            if not isinstance(el, dict):
                errors.append(f"{ewhere}: element must be an object")
                continue
            etype = el.get("type")
            if etype not in ELEMENT_TYPES:
                errors.append(f"{ewhere}: unknown type {etype!r}")
                continue
            rect = _rect(el.get("rect"))
            if rect is None:
                errors.append(f"{ewhere}: rect must be [x, y, width>0, height>0]")
            else:
                x, y, w, h = rect
                if x + w < 0 or y + h < 0 or x > cw or y > ch:
                    warnings.append(f"{ewhere}: rect is outside the canvas")
                elif x < 0 or y < 0 or x + w > cw or y + h > ch:
                    warnings.append(f"{ewhere}: rect extends beyond the canvas")

            if etype == "text":
                text = el.get("text")
                if not isinstance(text, str) or not text.strip():
                    errors.append(f"{ewhere}: text is empty")
                size = el.get("size", 120)
                if not _is_num(size) or float(size) <= 0:
                    errors.append(f"{ewhere}: size must be positive")
                mode = el.get("mode", "skeleton")
                if mode not in FONT_MODES:
                    errors.append(f"{ewhere}: mode must be one of {sorted(FONT_MODES)}")
                font = el.get("font") or "arefruqaa"
                try:
                    find_font(str(font))
                except Exception as exc:
                    errors.append(f"{ewhere}: font {font!r} not found ({exc})")
                rtl = el.get("rtl")
                if rtl is not None and not isinstance(rtl, bool):
                    errors.append(f"{ewhere}: rtl must be boolean")
                elif rtl is False and isinstance(text, str) and arabic.is_arabic(text):
                    # A plan written by a language model can carry rtl=false on
                    # Arabic text; the renderer then draws it left-to-right and
                    # the words come out reversed.  ``rtl`` absent means "auto"
                    # (the text pipeline decides from the first strong letter),
                    # so only an explicit false is a defect.
                    errors.append(
                        f"{ewhere}: Arabic text with rtl=false — "
                        "the words would be drawn left-to-right"
                    )
                weight = el.get("weight")
                if weight is not None and (not _is_num(weight) or not (100 <= int(weight) <= 900)):
                    errors.append(f"{ewhere}: weight must be 100..900")
            elif etype in ("svg", "image"):
                if check_assets and not _resolve_asset(el.get("asset"), pd):
                    errors.append(f"{ewhere}: asset not found: {el.get('asset')!r}")
            elif etype in ("texture", "background"):
                path = el.get("asset") or el.get("texture")
                if check_assets and not _resolve_asset(path, pd):
                    errors.append(f"{ewhere}: texture/background asset not found: {path!r}")
                opacity = el.get("opacity", 1.0)
                if not _is_num(opacity) or not (0 <= float(opacity) <= 1):
                    errors.append(f"{ewhere}: opacity must be 0..1")
                fit = el.get("fit", "cover")
                if fit not in ("cover", "contain"):
                    errors.append(f"{ewhere}: fit must be 'cover' or 'contain'")
                if rect and (abs(rect[0]) > 1 or abs(rect[1]) > 1 or abs(rect[2] - cw) > 2 or abs(rect[3] - ch) > 2):
                    warnings.append(f"{ewhere}: background/texture does not cover the full canvas")
            elif etype == "paper_card":
                style = el.get("style", "photo")
                if style not in CARD_STYLES:
                    errors.append(f"{ewhere}: card style must be one of {sorted(CARD_STYLES)}")
                border = el.get("border", 14)
                if not _is_num(border) or float(border) < 0:
                    errors.append(f"{ewhere}: border must be >= 0")
                texture = el.get("texture")
                if check_assets and texture and not _resolve_asset(texture, pd):
                    errors.append(f"{ewhere}: card texture not found: {texture!r}")
            elif etype == "torn_strip":
                col = el.get("paper_color")
                if col is not None and (not isinstance(col, (list, tuple)) or len(col) != 3 or not all(_is_num(v) for v in col)):
                    errors.append(f"{ewhere}: paper_color must be [r, g, b]")
            elif etype == "timeline":
                evs = el.get("events")
                if evs is not None and not isinstance(evs, list):
                    errors.append(f"{ewhere}: events must be a list")
            elif etype == "bars":
                vals = el.get("values")
                if vals is not None and not isinstance(vals, list):
                    errors.append(f"{ewhere}: values must be a list")
            total_elements += 1

    # Global timebase checks: the same helper the renderer uses, so validation
    # and rendering cannot disagree about scene boundaries.
    if rate is not None and scenes and not errors:
        try:
            bounds = scene_frame_bounds(plan)
            tb = plan.get("timebase")
            if isinstance(tb, dict):
                if tb.get("end_frame") is not None and int(tb["end_frame"]) != bounds[-1]["end_frame"]:
                    errors.append(
                        f"timebase.end_frame ({tb.get('end_frame')}) does not match scene bounds "
                        f"({bounds[-1]['end_frame']})"
                    )
                if tb.get("frames") is not None and int(tb["frames"]) != bounds[-1]["end_frame"]:
                    errors.append("timebase.frames does not match scene bounds")
                if tb.get("fps") is not None:
                    try:
                        tb_rate = coerce_frame_rate(tb["fps"])
                    except TimebaseError:
                        errors.append("timebase.fps is invalid")
                    else:
                        if tb_rate.value != rate.value:
                            errors.append("timebase.fps does not match plan fps")
            audio = plan.get("audio") or {}
            total_samples = int(audio.get("total_samples") or 0)
            if total_samples and scenes:
                last = scenes[-1]
                if last.get("end_sample") is not None and int(last["end_sample"]) != total_samples:
                    errors.append("scene sample bounds do not cover the full narration")
        except TimebaseError as exc:
            errors.append(f"timebase: {exc}")

    # These are warnings only: they do not block a render.
    for si, scene in enumerate(scenes, 1):
        if not isinstance(scene, dict):
            continue
        els = scene.get("elements") or []
        types = [e.get("type") for e in els if isinstance(e, dict)]
        if "background" in types and types.index("background") != 0:
            warnings.append(f"scene {scene.get('id', si)}: background should be the first element")
        if "texture" in types and types.index("texture") != 0:
            warnings.append(f"scene {scene.get('id', si)}: texture should be the first element")
        if str(plan.get("lang") or "").lower().startswith("en"):
            for e in els:
                if isinstance(e, dict) and e.get("type") == "text" and e.get("rtl") is True:
                    warnings.append(f"scene {scene.get('id', si)}: English text has rtl=true")

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "stats": {
            "scenes": len(scenes),
            "elements": total_elements,
            "duration": round(total_duration, 3),
        },
    }
