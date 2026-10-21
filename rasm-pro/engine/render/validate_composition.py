"""فحص تركيب المخطط: تداخل، حجم فعلي، تكرار، فراغ.

المخططات تُرسم على اللوح، فالعيب الذي لا يُرى في الجدول يُرى في الفيديو:
نصٌّ فوق صورة، أو نصٌّ صُغِّر حتى لا يُقرأ، أو مشهدان متتاليان بنفس
الشكل (تكرار يشبه «شريط كاذب»).

هذا الفحص **يقيس** الهندسة المرسومة فعلًا: حجم النص الطبيعي يُقاس
بالمسارات، ثم يُطبَّق نفس مقياس ``clip_strokes`` الذي يطبّقه الرندر (تصغير
وتوسيط داخل الصندوق)، فيقارَن الناتج بالصندوق وبقية العناصر.

يُستدعى من ``validate_plan`` (فتُرفض الخطة المعطوبة قبل الرندر) ومن
``tools/qa_composition.py`` (تقرير لكل مشروع).
"""
from __future__ import annotations

from typing import Any

OVERLAP_TOLERANCE = 6.0      # بكسل: تداخل أقل من هذا لا يُعدّ تداخلًا
MIN_EFFECTIVE_SIZE = 70.0    # أقل حجم خط مقروء على 720p
TEXT_TYPES = ("text",)
INK_TYPES = ("text", "image", "svg")


def _rect(element: dict) -> tuple[float, float, float, float]:
    """The element's box as (x, y, width, height)."""
    x, y, w, h = [float(v) for v in (element.get("rect") or [0, 0, 0, 0])]
    return (x, y, w, h)


def _edges(box: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    x, y, w, h = box
    return (x, y, x + w, y + h)


def text_geometry(element: dict) -> tuple[tuple[float, float, float, float], float] | None:
    """How a text element is really drawn: its box and the scale applied.

    The renderer does not clip text: it **scales** the glyphs to fit the
    element's box and centres them.  A caption that does not fit is drawn
    *smaller* — so the meaningful question is not "does it overflow" but
    "how small does it get".
    """
    text = str(element.get("text") or "")
    if not text.strip():
        return None
    try:
        from ..strokes import find_font, text_to_strokes

        doc = text_to_strokes(
            text,
            find_font(str(element.get("font") or "arefruqaa")),
            int(element.get("size") or 120),
            mode=str(element.get("mode") or "skeleton"),
            rtl=bool(element.get("rtl", False)),
        )
    except Exception:
        return None
    if not doc.strokes:
        return None
    rx, ry, rw, rh = _rect(element)
    sw, sh = float(doc.width or 1), float(doc.height or 1)
    scale = min(rw / sw, rh / sh) if sw and sh else 1.0
    ox = rx + (rw - sw * scale) / 2.0
    oy = ry + (rh - sh * scale) / 2.0
    xs = [ox + p[0] * scale for st in doc.strokes for p in st.points]
    ys = [oy + p[1] * scale for st in doc.strokes for p in st.points]
    return (min(xs), min(ys), max(xs), max(ys)), scale


def _overlap(a, b) -> float:
    """The overlap area of two boxes (edges)."""
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    w = min(ax1, bx1) - max(ax0, bx0)
    h = min(ay1, by1) - max(ay0, by0)
    if w <= OVERLAP_TOLERANCE or h <= OVERLAP_TOLERANCE:
        return 0.0
    return w * h


def _ink_area(element: dict) -> float:
    if element.get("type") == "text":
        geometry = text_geometry(element)
        if not geometry:
            return 0.0
        box, _ = geometry
        return (box[2] - box[0]) * (box[3] - box[1])
    x, y, w, h = _rect(element)
    return w * h


def _signature(scene: dict) -> str:
    return "|".join(
        [str(scene.get("role") or ""), str(scene.get("layout") or "")]
        + [str(e.get("type")) for e in (scene.get("elements") or []) if isinstance(e, dict)]
    )


def validate_scene(scene: dict, previous_signature: str | None = None) -> dict:
    """Measures one scene and returns its findings."""
    findings: list[dict] = []
    elements = [e for e in (scene.get("elements") or []) if isinstance(e, dict)]
    inked = [e for e in elements if e.get("type") in INK_TYPES]

    if not inked:
        findings.append({"kind": "empty-scene", "detail": "no text and no picture"})

    for element in elements:
        if element.get("type") != "text":
            continue
        geometry = text_geometry(element)
        if not geometry:
            continue
        _, scale = geometry
        size = float(element.get("size") or 120)
        effective = size * scale
        if scale < 0.75:
            findings.append(
                {
                    "kind": "text-shrunk",
                    "element": str(element.get("text") or "")[:40],
                    "scale": round(scale, 3),
                    "effective_size": round(effective, 1),
                }
            )
        if effective < MIN_EFFECTIVE_SIZE:
            findings.append(
                {
                    "kind": "text-too-small",
                    "element": str(element.get("text") or "")[:40],
                    "effective_size": round(effective, 1),
                    "floor": MIN_EFFECTIVE_SIZE,
                }
            )

    for index, a in enumerate(inked):
        if a.get("type") == "text":
            geometry = text_geometry(a)
            box_a = geometry[0] if geometry else None
        else:
            box_a = _edges(_rect(a))
        if not box_a:
            continue
        for b in inked[index + 1 :]:
            if b.get("type") == "text":
                geometry = text_geometry(b)
                box_b = geometry[0] if geometry else None
            else:
                box_b = _edges(_rect(b))
            if not box_b:
                continue
            area = _overlap(box_a, box_b)
            if area > 0:
                findings.append(
                    {
                        "kind": "element-overlap",
                        "a": a.get("type"),
                        "b": b.get("type"),
                        "area": round(area),
                    }
                )

    signature = _signature(scene)
    if previous_signature and signature == previous_signature:
        findings.append({"kind": "repeated-scene", "detail": signature})

    budget = scene.get("text_budget") or {}
    if budget and budget.get("fits") is False:
        findings.append(
            {
                "kind": "text-over-budget",
                "excess_words": budget.get("excess_words"),
                "capacity_words": budget.get("capacity_words"),
            }
        )

    return {
        "id": scene.get("id"),
        "role": scene.get("role"),
        "layout": scene.get("layout"),
        "elements": len(elements),
        "ink_area": round(sum(_ink_area(e) for e in elements)),
        "findings": findings,
    }


def validate_composition(plan: Any) -> dict:
    """The composition report of a whole plan."""
    scenes = (plan or {}).get("scenes") or []
    results: list[dict] = []
    previous: str | None = None
    for scene in scenes:
        result = validate_scene(scene, previous)
        for finding in result["findings"]:
            finding.setdefault("scene", result["id"])
        results.append(result)
        previous = _signature(scene)
    blocking = [
        finding
        for result in results
        for finding in result["findings"]
        if finding["kind"] in ("element-overlap", "text-too-small")
    ]
    warnings = [
        finding
        for result in results
        for finding in result["findings"]
        if finding["kind"] in ("repeated-scene", "text-over-budget", "text-shrunk", "empty-scene")
    ]
    return {
        "scenes": results,
        "blocking": blocking,
        "warnings": warnings,
        "ok": not blocking,
    }
