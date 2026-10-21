"""بناء الستوري بورد: ScriptGraph + نتائج البحث → خطة مشاهد قابلة للرندر.

المنطق (النسخة الأولى، قابلة للتطوير):
- مشهد 1 = عنوان كبير (الخطّاف) + سطر توضيحي.
- باقي المشاهد = عنصر بصري (صورة تُكشف أو SVG يُرسم) + تعليق نصي من جملة المشهد.
- كل العناصر موضوعة داخل منطقة آمنة بمعايير بصرية ثابتة، والزمن متسلسل.
"""
from __future__ import annotations

from fractions import Fraction
from pathlib import Path

from ..audio.align import load_alignment
from ..audio.narration import load_narration
from ..core import arabic
from ..core.timebase import (
    FrameRate,
    SampleRate,
    coerce_frame_rate,
    frame_rate_json,
    map_boundaries_to_frames,
)
from ..core.util import write_json
from .families import get_family, scene_role, text_budget

CANVAS = (2560, 1440)

# The drawing budget, measured on the production plan (2026-10-21):
# 106.92 s of natural drawing for a 79.875 s film (1.34x speed-up), which is
# ~0.95 drawn words per second of scene time.  A scene above that budget is
# reported as "does not fit" instead of being quietly rushed.
NATURAL_DRAWN_WORDS_PER_SECOND = 0.95
# A narration faster than this cannot be read (and cannot be drawn).
MAX_NARRATION_WORDS_PER_SECOND = 3.2
SAFE = 130
INK = "#211E1A"
ACCENT = "#8C2F1F"


def _first_clause(text: str, words: int = 8) -> str:
    parts = (text or "").strip().split()
    out = " ".join(parts[:words]).strip(" ،,.…")
    if not out:
        return ""
    return out + ("…" if len(parts) > words else "")


def _wrap(text: str, per_line: int) -> str:
    """يلف النص لأسطر قصيرة (خط أكبر وأوضح + كاميرا أوضح)."""
    parts = (text or "").strip().split()
    if not parts:
        return ""
    return "\n".join(" ".join(parts[i : i + per_line]) for i in range(0, len(parts), per_line))


def _index_assets(research: dict) -> dict[str, list[dict]]:
    """فهرس: كيان (مُطبَّع) → أصول صوره/أيقوناته."""
    index: dict[str, list[dict]] = {}
    for e in research.get("entities", []) or []:
        name = arabic.normalize(e.get("name") or "")
        if not name:
            continue
        bucket = index.setdefault(name, [])
        for a in e.get("assets", []) or []:
            rec = a.get("asset") or {}
            path = rec.get("path")
            if not path:
                continue
            mime = str(rec.get("mime") or "")
            ext = Path(path).suffix.lower()
            if not (mime.startswith("image/") or ext in (".jpg", ".jpeg", ".png", ".webp", ".svg", ".gif", ".tif", ".tiff")):
                continue
            bucket.append(
                {
                    "path": path,
                    "ext": ext,
                    "vector": ext == ".svg",
                    "need": rec.get("need"),
                    "title": rec.get("title"),
                    "license": rec.get("license"),
                    "entity": e.get("name"),
                }
            )
    return index


def _abs_path(path: str, base: Path) -> str:
    p = Path(path)
    if p.is_absolute():
        return str(p)
    return str((base / p).resolve())


def _scene_entities(scene: dict, index: dict[str, list[dict]]) -> list[str]:
    nn = arabic.normalize(scene.get("narration") or "")
    hits: list[str] = []
    for name in index:
        if name and name in nn and name not in hits:
            hits.append(name)
    return hits


def _scene_text_chunks(
    role: str,
    graph: dict,
    narration: str,
    visual: dict | None,
    names: list[str],
) -> list[str]:
    """The text pieces a scene may show, in reading order (may be empty)."""
    hook = (graph.get("hook") or narration).strip()
    if role == "hook":
        title = _first_clause(hook, 5) or _first_clause(narration, 5)
        # the subtitle of a hook is short on purpose: it has to be drawn
        sub = _first_clause(narration, 6)
        return [t for t in (title, sub if sub != title else "") if t]
    caption = _first_clause(narration, 7)
    if role == "evidence" and visual:
        label = visual.get("entity") or (names[0] if names else "")
        return [t for t in (label, caption) if t]
    return [caption] if caption else []


def _text_slot(
    role: str,
    slot: int,
    *,
    english: bool,
    title_size: int,
    sub_size: int,
    label_size: int,
    caption_size: int,
    headline_size: int,
) -> tuple[dict, int, int]:
    """Where a text element goes and how big it is (per role and slot)."""
    if role == "hook" and slot == 1:
        return {"rect": [SAFE, 220, CANVAS[0] - 2 * SAFE, 720], "color": INK, "weight": 650}, title_size, 4
    if role == "hook" and slot == 2:
        return (
            {"rect": [SAFE + 60, 940, CANVAS[0] - 2 * SAFE - 120, 340], "color": ACCENT, "weight": 500},
            sub_size,
            6,
        )
    if role == "label":
        return {"rect": [1450, 150, 980, 190], "color": ACCENT, "weight": 500}, label_size, 3
    if role == "evidence" and slot == 2:
        return {"rect": [1520, 400, 920, 740], "color": INK, "weight": 500}, caption_size, 4
    return {"rect": [SAFE, 380, CANVAS[0] - 2 * SAFE, 700], "color": INK, "weight": 600}, headline_size, 4


def _text_element(
    text: str,
    *,
    role: str,
    slot: int,
    font: str,
    english: bool,
    place: dict,
    size: int,
    wrap: int,
) -> dict:
    """A text element placed for its role (title / subtitle / label / caption)."""
    return {
        "type": "text",
        "text": _wrap(text, wrap),
        "font": font,
        "size": size,
        "rect": list(place["rect"]),
        "mode": "skeleton",
        "rtl": not english,
        **({"weight": int(place["weight"])} if english else {}),
        "color": place["color"],
        "gap": 0.3,
    }


def build_plan(
    graph: dict,
    research: dict,
    *,
    project_dir: Path | None = None,
    max_scenes: int | None = None,
    fps: FrameRate | int | float | str | dict | None = None,
    family: str | None = None,
) -> dict:
    base = Path(project_dir) if project_dir else Path(".")
    # قاعدة زمن واحدة: المشروع يحدد المعدل، والافتراضي 24 (لا 30 ثابتة).
    rate = coerce_frame_rate(fps) if fps is not None else FrameRate(24)
    fam = get_family(family)
    index = _index_assets(research)
    scenes = list(graph.get("scenes", []))[: (max_scenes or 10_000)]
    out_scenes: list[dict] = []
    english = str(graph.get("lang") or "ar").lower().startswith("en")
    title_font = "inter" if english else "arefruqaa"
    body_font = "inter" if english else "cairo"
    title_size = 220 if english else 260
    sub_size = 112 if english else 128
    label_size = 86 if english else 96
    caption_size = 140 if english else 150
    headline_size = 180 if english else 190

    for i, s in enumerate(scenes, 1):
        narration = (s.get("narration") or "").strip()
        elements: list[dict] = []

        names = _scene_entities(s, index)
        assets: list[dict] = []
        for n in names:
            assets += index.get(n, [])
        photo = next((a for a in assets if not a["vector"]), None)
        vector = next((a for a in assets if a["vector"]), None)
        visual = photo or vector
        if not fam.allows_images:
            visual = None

        role = scene_role(i, len(scenes))
        recipe = fam.recipe.get(role) or fam.recipe.get("explain", ())
        text_chunks = _scene_text_chunks(role, graph, narration, visual, names)
        text_index = 0
        for kind in recipe:
            if kind == "text":
                chunk = text_chunks[text_index] if text_index < len(text_chunks) else None
                text_index += 1
                if not chunk:
                    continue
                place, size, wrap = _text_slot(
                    role,
                    text_index,
                    english=english,
                    title_size=title_size,
                    sub_size=sub_size,
                    label_size=label_size,
                    caption_size=caption_size,
                    headline_size=headline_size,
                )
                elements.append(
                    _text_element(
                        chunk,
                        role=role,
                        slot=text_index,
                        font=body_font if text_index > 1 else title_font,
                        english=english,
                        place=place,
                        size=size,
                        wrap=wrap,
                    )
                )
            elif kind == "highlight":
                # شريط تظليل خلف النص (اللون الفاتح) — يُرسم قبل النص
                elements.append(
                    {
                        "type": "highlight",
                        "rect": [150, 300, 2240, 340],
                        "color": "#F3D57C",
                        "speed": 2.2,
                        "events": False,
                        "gap": 0.14,
                    }
                )
            elif kind == "underline":
                # في مشهد الافتتاحية يُرسَم التسطير تحت العنوان الفرعي،
                # وإلا criss-cross على ذيل الخط العربي.
                rect = [130, 1290, 2300, 260] if role == "hook" else [130, 285, 2300, 380]
                elements.append(
                    {
                        "type": "underline",
                        "rect": rect,
                        "double": True,
                        "color": "#8C2F1F",
                        "brush": 6.5,
                        "offset": 16,
                        "gap": 0.3,
                    }
                )
            elif kind == "flourish":
                elements.append(
                    {
                        "type": "flourish",
                        "rect": [190, 950, 2180, 340],
                        "color": "#8C2F1F",
                        "gap": 0.2,
                    }
                )
            elif kind == "torn_strip":
                label = (visual.get("entity") if visual else None) or (names[0] if names else "")
                elements.append(
                    {
                        "type": "torn_strip",
                        "rect": [1420, 130, 1030, 250],
                        "seed": 21,
                        "tilt": -0.6,
                        "gap": 0.12,
                        **({"text": label, "font": body_font, "size": label_size} if label else {}),
                    }
                )
            elif kind in ("image", "svg"):
                if not visual:
                    continue
                visual_rect = [SAFE - 20, 330, 1400, 950]
                if visual["vector"]:
                    elements.append(
                        {
                            "type": "svg",
                            "asset": _abs_path(visual["path"], base),
                            "rect": visual_rect,
                            "gap": 0.35,
                        }
                    )
                else:
                    elements.append(
                        {
                            "type": "image",
                            "asset": _abs_path(visual["path"], base),
                            "rect": visual_rect,
                            "trace_size": 950,
                            "gap": 0.35,
                        }
                    )
            elif kind == "paper_card":
                elements.append(
                    {
                        "type": "paper_card",
                        "rect": [SAFE - 60, 300, 1520, 1000],
                        "style": "photo",
                        "gap": 0.12,
                    }
                )
            elif kind in ("timeline", "bars"):
                data = s.get("data") or {}
                if kind == "timeline" and data.get("events"):
                    elements.append(
                        {
                            "type": "timeline",
                            "rect": [SAFE, 880, CANVAS[0] - 2 * SAFE, 420],
                            "events": data["events"],
                            "font": body_font,
                            "size": 64,
                            "rtl": not english,
                            "gap": 0.25,
                        }
                    )
                elif kind == "bars" and data.get("values"):
                    elements.append(
                        {
                            "type": "bars",
                            "rect": [SAFE, 880, CANVAS[0] - 2 * SAFE, 420],
                            "values": data["values"],
                            "labels": data.get("labels") or [],
                            "font": body_font,
                            "size": 60,
                            "rtl": not english,
                            "gap": 0.25,
                        }
                    )
                else:
                    # no data for this scene: the slot is not filled
                    continue

        # the narration must be readable on screen: keep the label of the
        # evidence visible next to the picture
        if role in ("evidence",) and visual and "text" in recipe:
            label = visual.get("entity") or (names[0] if names else "")
            if label and not any(el.get("type") == "text" for el in elements):
                elements.insert(
                    0,
                    _text_element(
                        label,
                        role="label",
                        slot=0,
                        font=body_font,
                        size=label_size,
                        english=english,
                        accent=ACCENT,
                    ),
                )

        out_scenes.append(
            {
                "id": s.get("id", i),
                "duration": float(s.get("duration") or 6.0),
                "narration": narration,
                "role": role,
                "needs": s.get("needs", []),
                "assets_used": [a["path"] for a in assets[:3]],
                "elements": elements,
            }
        )

    # ————— الصوت هو الساعة: عند وجود تعليق صوتي/محاذاة، المدد تُشتق منها —————
    audio_info = None
    timing: dict = {"source": "estimated", "method": "words-per-second"}
    nar = load_narration(base) if project_dir else None
    if nar:
        audio_info = {
            "file": nar.get("path"),
            "sha256": nar.get("sha256"),
            "duration_sec": nar.get("duration_sec"),
            "duration_exact": nar.get("duration_exact"),
            "sample_rate": nar.get("sample_rate"),
            "total_samples": nar.get("total_samples"),
            "codec": nar.get("codec"),
        }

    def _assign_estimated_frames() -> int:
        """Assign absolute frames from exact decimal durations, once."""
        acc = Fraction(0)
        total = 0
        for sc in out_scenes:
            dur = Fraction(str(sc.get("duration") or 0))
            start = rate.frame_of_time(acc, mode="round")
            acc += dur
            end = rate.frame_of_time(acc, mode="round")
            sc["start_frame"] = start
            sc["end_frame"] = end
            sc["duration_frames"] = end - start
            sc["duration"] = round(float(dur), 6)
            total = end
        return total

    total_frames = _assign_estimated_frames()

    # ميزانية الرسم: النص **المرسوم على الشاشة** يجب أن يُرسم ضمن مدة المشهد.
    # المعامل مقيس على خطة الإنتاج: ~0.95 كلمة مرسومة في الثانية (القياس:
    # 106.92ث رسم طبيعي مقابل 79.875ث فيلم => 1.34× تسريع).
    words_limit = text_budget(fam)
    over_budget = 0
    for sc in out_scenes:
        drawn_words = sum(
            len(str(el.get("text") or "").replace("\n", " ").split())
            for el in sc.get("elements") or []
            if el.get("type") == "text"
        )
        narration_words = len((sc.get("narration") or "").split())
        duration = max(0.1, float(sc.get("duration") or 0.0))
        capacity = duration * NATURAL_DRAWN_WORDS_PER_SECOND
        excess = max(0, drawn_words - int(capacity))
        narration_rate = narration_words / duration
        sc["text_budget"] = {
            "drawn_words": drawn_words,
            "narration_words": narration_words,
            "narration_words_per_second": round(narration_rate, 3),
            "natural_words_per_second": NATURAL_DRAWN_WORDS_PER_SECOND,
            "capacity_words": int(capacity),
            "fits": excess == 0 and narration_rate <= MAX_NARRATION_WORDS_PER_SECOND,
            "excess_words": excess,
            "family_limit": words_limit,
            "over_family_limit": drawn_words > words_limit,
        }
        if not sc["text_budget"]["fits"]:
            over_budget += 1

    al = load_alignment(base) if project_dir else None
    if al and al.segments and al.sample_rate > 0:
        by_id = {int(seg.scene_id): seg for seg in al.segments}
        segs = [by_id.get(int(sc["id"])) for sc in out_scenes]
        # Only accept a complete, contiguous alignment. A partial alignment is
        # reported as estimated rather than mixed into some scenes silently.
        complete = all(seg is not None and seg.length > 0 for seg in segs)
        if complete:
            starts = [int(seg.start_sample) for seg in segs]  # type: ignore[union-attr]
            ends = [int(seg.end_sample) for seg in segs]  # type: ignore[union-attr]
            contiguous = starts[0] == 0 and all(
                ends[i] == starts[i + 1] for i in range(len(starts) - 1)
            ) and ends[-1] == int(al.total_samples)
            if contiguous:
                mapped = map_boundaries_to_frames(
                    [starts[0], *ends],
                    SampleRate(al.sample_rate),
                    rate,
                    total_samples=al.total_samples,
                    mode="round",
                )
                for i, sc in enumerate(out_scenes):
                    seg = segs[i]
                    assert seg is not None
                    sc["start_sample"] = starts[i]
                    sc["end_sample"] = ends[i]
                    sc["duration_samples"] = ends[i] - starts[i]
                    sc["start_frame"] = mapped[i]
                    sc["end_frame"] = mapped[i + 1]
                    sc["duration_frames"] = mapped[i + 1] - mapped[i]
                    sc["duration"] = round((ends[i] - starts[i]) / al.sample_rate, 6)
                total_frames = mapped[-1]
                timing = {
                    "source": "narration",
                    "level": al.level,
                    "method": al.method,
                    "notes": al.notes,
                    "sample_rate": al.sample_rate,
                    "total_samples": al.total_samples,
                    "fps": frame_rate_json(rate),
                    "alignment": str(base / "audio" / "alignment.json"),
                    "rounding": "absolute-samples-to-frames",
                }
            else:
                timing["note"] = "المحاذاة غير متصلة أو لا تغطي كامل الصوت — استُخدم التوقيت التقديري."
        else:
            timing["note"] = "المحاذاة لا تغطي كل المشاهد — استُخدم التوقيت التقديري."
    elif audio_info:
        timing = {
            "source": "estimated-with-narration",
            "method": "words-per-second",
            "note": "يوجد تعليق صوتي بلا محاذاة — المدد تقديرية وقد تختلف عن الصوت.",
            "fps": frame_rate_json(rate),
        }

    exact_duration = sum(
        (Fraction(str(sc["duration"])) for sc in out_scenes),
        Fraction(0),
    )
    return {
        "project": graph.get("source_hash", ""),
        "lang": graph.get("lang", "ar"),
        "canvas": list(CANVAS),
        "fps": frame_rate_json(rate),
        "family": {
            "name": fam.name,
            "description": fam.description,
            "words_per_scene": words_limit,
            "allows_images": fam.allows_images,
            "motion": {
                "zoom": fam.motion.zoom,
                "follow": fam.motion.follow,
                "zoom_by_type": dict(fam.motion.zoom_by_type),
                "hold_on_text": fam.motion.hold_on_text,
                "lead_in": fam.motion.lead_in,
            },
        },
        "timebase": {
            "source": timing["source"],
            "method": timing.get("method", ""),
            "rounding": timing.get("rounding", "absolute-boundaries"),
            "fps": frame_rate_json(rate),
            "sample_rate": timing.get("sample_rate"),
            "total_samples": timing.get("total_samples"),
            "start_frame": 0,
            "end_frame": total_frames,
            "frames": total_frames,
        },
        "scenes": out_scenes,
        "audio": audio_info,
        "timing": timing,
        "stats": {
            "scenes": len(out_scenes),
            "elements": sum(len(s["elements"]) for s in out_scenes),
            "estimated_duration": round(float(exact_duration), 1),
            "duration": round(float(exact_duration), 6),
            "frames": total_frames,
            "scenes_over_text_budget": over_budget,
        },
    }


def save_plan(plan: dict, project_dir: Path, *, prefer: str = "plan.json") -> Path:
    """Save a plan under a name that is **never reused**.

    A plan is production data: the legacy ``plan.json`` and the active
    ``plan_v2.json`` must survive any rebuild.  So a new plan takes the first
    free name in the sequence (``plan.json`` → ``plan_v2.json`` → …) and the
    caller activates it explicitly.  Nothing is ever overwritten silently.
    """
    d = Path(project_dir) / "storyboard"
    d.mkdir(parents=True, exist_ok=True)
    candidate = d / prefer
    if candidate.exists():
        stem, dot, ext = prefer.partition(".")
        n = 2
        while (d / f"{stem}_v{n}{dot}{ext}").exists():
            n += 1
        candidate = d / f"{stem}_v{n}{dot}{ext}"
    return write_json(candidate, plan)
