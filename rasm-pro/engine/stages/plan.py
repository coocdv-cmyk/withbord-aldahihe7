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
from ..core.timebase import FrameRate, coerce_frame_rate, frame_rate_json
from ..core.util import write_json

CANVAS = (2560, 1440)
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


def build_plan(
    graph: dict,
    research: dict,
    *,
    project_dir: Path | None = None,
    max_scenes: int | None = None,
    fps: FrameRate | int | float | str | dict | None = None,
) -> dict:
    base = Path(project_dir) if project_dir else Path(".")
    # قاعدة زمن واحدة: المشروع يحدد المعدل، والافتراضي 24 (لا 30 ثابتة).
    rate = coerce_frame_rate(fps) if fps is not None else FrameRate(24)
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

        if i == 1:
            hook = (graph.get("hook") or narration).strip()
            title = _first_clause(hook, 5) or _first_clause(narration, 5)
            if title:
                elements.append(
                    {
                        "type": "text",
                        "text": _wrap(title, 4),
                        "font": title_font,
                        "size": title_size,
                        "rect": [SAFE, 220, CANVAS[0] - 2 * SAFE, 720],
                        "mode": "skeleton",
                        "rtl": not english,
                        **({"weight": 650} if english else {}),
                        "color": INK,
                        "gap": 0.3,
                    }
                )
            sub = _first_clause(narration, 12)
            if sub and sub != title:
                elements.append(
                    {
                        "type": "text",
                        "text": _wrap(sub, 6),
                        "font": body_font,
                        "size": sub_size,
                        "rect": [SAFE + 60, 940, CANVAS[0] - 2 * SAFE - 120, 340],
                        "mode": "skeleton",
                        "rtl": not english,
                        **({"weight": 500} if english else {}),
                        "color": ACCENT,
                        "gap": 0.4,
                    }
                )
        else:
            caption = _first_clause(narration, 7)
            if visual:
                label = visual.get("entity") or (names[0] if names else "")
                if label:
                    elements.append(
                        {
                            "type": "text",
                            "text": label,
                            "font": body_font,
                            "size": label_size,
                            "rect": [1450, 150, 980, 190],
                            "mode": "skeleton",
                            "rtl": not english,
                            **({"weight": 500} if english else {}),
                            "color": ACCENT,
                            "gap": 0.2,
                        }
                    )
                visual_rect = [SAFE - 20, 330, 1400, 950]
                if visual["vector"]:
                    elements.append({"type": "svg", "asset": _abs_path(visual["path"], base), "rect": visual_rect, "gap": 0.35})
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
                if caption:
                    elements.append(
                        {
                            "type": "text",
                            "text": _wrap(caption, 4),
                            "font": body_font,
                            "size": caption_size,
                            "rect": [1520, 400, 920, 740],
                            "mode": "skeleton",
                            "rtl": not english,
                            **({"weight": 500} if english else {}),
                            "color": INK,
                            "gap": 0.3,
                        }
                    )
            elif caption:
                elements.append(
                    {
                        "type": "text",
                        "text": caption,
                        "font": title_font,
                        "size": headline_size,
                        "rect": [SAFE, 380, CANVAS[0] - 2 * SAFE, 700],
                        "mode": "skeleton",
                        "rtl": not english,
                        **({"weight": 600} if english else {}),
                        "color": INK,
                        "gap": 0.3,
                    }
                )

        out_scenes.append(
            {
                "id": s.get("id", i),
                "duration": float(s.get("duration") or 6.0),
                "narration": narration,
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
            "sample_rate": nar.get("sample_rate"),
            "total_samples": nar.get("total_samples"),
            "codec": nar.get("codec"),
        }
    al = load_alignment(base) if project_dir else None
    if al and al.segments and al.sample_rate > 0:
        by_id = {int(seg.scene_id): seg for seg in al.segments}
        for sc in out_scenes:
            seg = by_id.get(int(sc["id"]))
            if not seg or seg.length <= 0:
                continue
            # المصدر: عينات مطلقة. لا نمدّ مقطعًا قصيرًا قسرًا لأن ذلك
            # يكسر مزامنة الصوت؛ نترك الطول الحقيقي ونصرّح بالتحذير.
            sc["start_sample"] = int(seg.start_sample)
            sc["end_sample"] = int(seg.end_sample)
            sc["duration_samples"] = int(seg.length)
            sc["duration_frames"] = rate.frames_for_duration(
                Fraction(seg.length, al.sample_rate), mode="round"
            )
            sc["duration"] = round(seg.length / al.sample_rate, 6)
        timing = {
            "source": "narration",
            "level": al.level,
            "method": al.method,
            "notes": al.notes,
            "sample_rate": al.sample_rate,
            "total_samples": al.total_samples,
            "fps": frame_rate_json(rate),
            "alignment": str(base / "audio" / "alignment.json"),
        }
    elif audio_info:
        timing = {
            "source": "estimated-with-narration",
            "method": "words-per-second",
            "note": "يوجد تعليق صوتي بلا محاذاة — المدد تقديرية وقد تختلف عن الصوت.",
        }

    return {
        "project": graph.get("source_hash", ""),
        "lang": graph.get("lang", "ar"),
        "canvas": list(CANVAS),
        "fps": frame_rate_json(rate),
        "scenes": out_scenes,
        "audio": audio_info,
        "timing": timing,
        "stats": {
            "scenes": len(out_scenes),
            "elements": sum(len(s["elements"]) for s in out_scenes),
            "estimated_duration": round(sum(s["duration"] for s in out_scenes), 1),
        },
    }


def save_plan(plan: dict, project_dir: Path) -> Path:
    return write_json(Path(project_dir) / "storyboard" / "plan.json", plan)
