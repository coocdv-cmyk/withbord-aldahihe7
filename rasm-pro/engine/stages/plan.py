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
from .families import get_family, resolve_roles, scene_role, text_budget

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
MUTED = "#6B5B4A"      # سطر التفاصيل: أهدأ من الأسود


def _first_clause(text: str, words: int = 8) -> str:
    """أول ``words`` كلمة من الجملة — مع قطعٍ **عند حدود الجملة** لا داخلها.

    الت都应该 أن تُقرأ جملةٌ كاملة على الشاشة: فإذا اقتضى القطع، فليكن عند
    أقرب فاصلة (أو نقطتين) قبل الحدّ، لا في منتصف العبارة.
    """
    parts = (text or "").strip().split()
    if not parts:
        return ""
    if len(parts) <= words:
        return " ".join(parts).strip(" ،,.…")
    head = parts[:words]
    for index in range(len(head) - 1, 0, -1):
        if head[index - 1].endswith((",", "،", ";", "؛", ":", "،")):
            return " ".join(head[:index]).strip(" ،,.…") + "…"
    return " ".join(head).strip(" ،,.…") + "…"


def _wrap(text: str, per_line: int) -> str:
    """يلف النص لأسطر قصيرة (خط أكبر وأوضح + كاميرا أوضح)."""
    parts = (text or "").strip().split()
    if not parts:
        return ""
    return "\n".join(" ".join(parts[i : i + per_line]) for i in range(0, len(parts), per_line))


_WIDTH_CACHE: dict[tuple[str, int], object] = {}


def _measure_font(font_name: str, size: int):
    """يمسك مقياس الخط (PIL) لقياس عرض النص قبل رسمه."""
    key = (str(font_name), int(size))
    if key in _WIDTH_CACHE:
        return _WIDTH_CACHE[key]
    font = None
    try:
        from PIL import ImageFont

        from ..strokes import find_font

        font = ImageFont.truetype(str(find_font(font_name)), int(size))
    except Exception:
        font = None
    _WIDTH_CACHE[key] = font
    return font


def _text_width(text: str, font_name: str, size: int) -> float:
    """The natural width of a (wrapped) text line, in canvas units."""
    font = _measure_font(font_name, size)
    if font is None:
        return float(len(text or "")) * float(size) * 0.5
    width = 0.0
    for line in str(text or "").split("\n"):
        try:
            width = max(width, float(font.getlength(line)))
        except Exception:
            width = max(width, len(line) * float(size) * 0.5)
    return width


def _natural_size(lines: list[str], font_name: str, size: int) -> tuple[float, float]:
    """The natural size of a wrapped text (width, height) in canvas units."""
    font = _measure_font(font_name, size)
    width = 0.0
    for line in lines:
        try:
            width = max(width, float(font.getlength(line)) if font else len(line) * size * 0.5)
        except Exception:
            width = max(width, len(line) * float(size) * 0.5)
    return width, len(lines) * float(size) * 1.42


def _fit_text(
    text: str,
    *,
    font_name: str,
    size: int,
    box_w: float,
    box_h: float,
    min_size: float = 78.0,
) -> str:
    """Wraps the text and **shortens** it until it can be read at its size.

    The renderer scales a text down when it does not fit its box — and a text
    scaled below the reading floor is unreadable.  So the plan drops words (and
    marks the cut) instead of drawing a caption nobody can read.
    """
    words = str(text or "").split()
    if not words:
        return ""
    while True:
        body = _wrap_to_width(" ".join(words), font_name=font_name, size=size, width=box_w)
        lines = body.split("\n")
        nat_w, nat_h = _natural_size(lines, font_name, size)
        scale = 1.0
        if nat_w > 0 and nat_h > 0:
            scale = min(1.0, box_w / nat_w, box_h / nat_h)
        if size * scale >= min_size or len(words) <= 2:
            if words != str(text or "").split():
                body = body.rstrip() + "…"
            return body
        words = words[:-1]


def _band_for(text: str, *, font_name: str, size: int, base: list[float], pad: int = 26) -> list[float]:
    """A highlight band that follows the **measured** width of its text.

    The band never grows past the width the layout gives it: a long title must
    not push the band over the character standing next to it.
    """
    x, y, w, h = [float(v) for v in base]
    width = _text_width(text, font_name, size)
    target = min(float(w), max(width + pad * 2, w * 0.35))
    return [x, y, target, h]


def _wrap_to_width(text: str, *, font_name: str, size: int, width: float) -> str:
    """تغليف النص **بقياس العرض** حتى لا يتجاوز صندوقه.

    التغليف بعدد كلمات ثابت ترك النص يتجاوز العمود فيُقصّ على الشاشة
    (سطر «dug up in 1972» في عمود 920px).  هنا نقيس كل سطر بالخط الحقيقي
    (PIL) ولا نضع كلمة لا يسعها العرض.
    """
    parts = (text or "").strip().split()
    if not parts:
        return ""
    font = _measure_font(font_name, size)
    if font is None or width <= 0:
        return _wrap(text, 6)
    limit = float(width)
    lines: list[str] = []
    current: list[str] = []
    for word in parts:
        trial = " ".join([*current, word])
        try:
            w = float(font.getlength(trial))
        except Exception:
            w = len(trial) * float(size) * 0.5
        if current and w > limit:
            lines.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        lines.append(" ".join(current))
    return "\n".join(lines)


def _rejected_asset_paths(project_dir: Path | None) -> set[str]:
    """مسارات الأصول التي رفضها إنسان (من سجل القرارات الملحق فقط)."""
    if not project_dir:
        return set()
    try:
        from ..core.assets import decisions_by_asset

        out: set[str] = set()
        for records in decisions_by_asset(project_dir).values():
            for record in records or []:
                if str((record or {}).get("decision") or "") != "rejected":
                    continue
                path = str((record or {}).get("path") or "").replace("\\", "/")
                if path:
                    out.add(path)
        return out
    except Exception:
        return set()


def _index_assets(research: dict, rejected: set[str] | None = None) -> dict[str, list[dict]]:
    """فهرس: كيان (مُطبَّع) → أصول صوره/أيقوناته.

    ``rejected`` = المسارات التي رفضها إنسان.  **الأصل المرفوض لا يدخل الخطة
    أصلًا**: البحث يجد بالاسم وقد يُرجع صورة لا تمثّل الكيان (قطار، سفينة حديثة)؛
    الرفض قرار بشري، والخطة لا تختار أصلًا مرفوضًا.
    """
    index: dict[str, list[dict]] = {}
    rejected = rejected or set()
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
            if str(path).replace("\\", "/") in rejected:
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
                    "entity_type": rec.get("entity_type"),
                    "mime": mime,
                }
            )
    return index


def _apply_rejection_rules(index: dict[str, list[dict]], project_dir: Path | None) -> dict:
    """يحذف الأصول التي تحجبها قواعد الرفض المتعلَّمة من قراراتك.

    القاعدة: العنوان الذي يحمل رمزًا مميِّزًا لأصلٍ رفضته أنت (قطار، سفينة،
    خريطة تضاريس…) **لا يدخل الخطة** — حتى لو جاء من بحث جديد.  هذا ما يوقف
    تكرار الرفض اليدوي في كل حلقة.
    """
    report = {"rules": 0, "blocked": []}
    if not project_dir:
        return report
    try:
        from ..memory.rejections import filter_assets, rules_for

        rules = rules_for(project_dir)
    except Exception:
        return report
    if not rules:
        return report
    report["rules"] = len(rules)
    for name, assets in list(index.items()):
        allowed, blocked = filter_assets(assets, rules)
        index[name] = allowed
        for item in blocked:
            report["blocked"].append(
                {
                    "entity": name,
                    "path": item.get("path"),
                    "title": item.get("title"),
                    "reason": item.get("blocked_reason"),
                }
            )
    return report


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
    capacity: int | None = None,
) -> list[str]:
    """The text pieces a scene may show, in reading order (may be empty).

    ``capacity`` = how many words can be **drawn** inside this scene
    (the measured budget: ~0.95 drawn words per second).  The on-screen
    text never exceeds it, so a short scene gets a short caption instead of
    an over-budget one — and a long scene is not limited to seven words.
    """
    cap = max(1, int(capacity)) if capacity else 7
    hook = (graph.get("hook") or narration).strip()
    if role == "hook":
        title_words = max(2, min(5, cap - 2))
        title = _first_clause(hook, title_words) or _first_clause(narration, title_words)
        # The subtitle continues the sentence instead of repeating the title.
        spoken = narration.split()
        used = len(title.split())
        rest = " ".join(spoken[used:]) if len(spoken) > used else ""
        sub_words = max(0, min(6, cap - used))
        sub = _first_clause(rest, sub_words) if (rest and sub_words) else ""
        if (not sub or len(sub.replace("…", "").split()) < 2) and title.endswith("…"):
            # the title was cut and the rest of the sentence is too thin:
            # take the **next sentence** instead of a fragment
            sentences = arabic.split_sentences(narration)
            if len(sentences) > 1:
                sub = _first_clause(sentences[1], max(2, min(6, cap - title_words)))
        return [t for t in (title, sub if sub and sub != title else "") if t]
    label = ""
    if role == "evidence" and visual:
        label = visual.get("entity") or (names[0] if names else "")
    label_words = len(label.split()) if label else 0
    # the caption may use the whole drawing capacity of the scene; the
    # **measured** wrap decides how it breaks into lines, so a long caption
    # is no longer cut at a fixed word count ("... dug up in" without 1972).
    caption_words = max(1, min(12, cap - label_words))
    caption = _first_clause(narration, caption_words)
    if role == "evidence" and visual and label:
        return [label, caption]
    if role == "explain" and caption:
        # a statement + a quieter detail line: the board carries a hierarchy.
        # The statement is the first **sentence** (cut with an ellipsis if the
        # scene is too short for it) and the detail is the next one.
        sentences = arabic.split_sentences(narration)
        head_words = max(2, min(6, cap))
        head = " ".join((sentences[0] if sentences else caption).split()[:head_words]).rstrip(" .,،:;")
        if sentences and len(sentences[0].split()) > head_words:
            head = head + "…"
        room = max(0, cap - head_words)
        detail = ""
        if len(sentences) > 1 and room >= 3:
            take = min(6, room)
            detail = " ".join(sentences[1].split()[:take]).rstrip(" .,،:;")
            if len(sentences[1].split()) > take:
                detail = detail + "…"
        if detail and len(detail.split()) >= 2:
            return [head, detail]
        return [head] if head else []
    return [caption] if caption else []


FIGURE_POSES = ("think", "focus", "point", "read", "like", "cheer", "idle")

# words that decide how the character reacts to the line
FIGURE_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("?", "؟", "هل", "لماذا", "كيف", "why", "how", "what"), "think"),
    (("لأن", "لذلك", "إذًا", "إذن", "السبب", "السببية", "because", "therefore"), "focus"),
    (("اقرأ", "اكتب", "اكتب ملاحظة", "دوّن", "write", "read", "note"), "read"),
    (("أعجب", "يعجب", "قوة", "قوية", "قوي", "مذهل", "amazing", "powerful"), "like"),
)


def _figure_pose(narration: str, role: str) -> str:
    """الوضعية التي يتفاعل بها الشخصية مع معنى الجملة."""
    low = " ".join(str(narration or "").lower().split())
    if role == "close":
        return "cheer"
    for markers, pose in FIGURE_RULES:
        if any(marker in low for marker in markers):
            return pose
    return "point"


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
    has_visual: bool = False,
    variant: str = "a",
) -> tuple[dict, int, int]:
    """Where a text element goes and how big it is (per role, slot, variant)."""
    lay = _layout(role, variant)
    if role == "hook":
        if slot == 1:
            return {"rect": list(lay["title"]), "color": INK, "weight": 650}, title_size, 4
        return (
            {"rect": list(lay["sub"]), "color": ACCENT, "weight": 500},
            sub_size,
            6,
        )
    if role == "label":
        return {"rect": list(lay["label"]), "color": ACCENT, "weight": 500}, label_size, 3
    if role == "evidence" and has_visual and slot == 1:
        # the entity label belongs on the torn strip, not as a giant headline
        # on top of the image.  The caption is the second text slot.
        return {"rect": list(lay["label"]), "color": ACCENT, "weight": 500}, label_size, 3
    if role == "evidence" and slot == 2:
        return {"rect": list(lay["caption"]), "color": INK, "weight": 500}, caption_size, 4
    if role == "explain" and slot == 2:
        # the detail line under the statement: smaller, quieter
        return {"rect": list(lay["detail"]), "color": MUTED, "weight": 500}, max(60, headline_size // 2), 8
    return {"rect": list(lay["statement"]), "color": INK, "weight": 600}, headline_size, 4


# --------------------------------------------------------------------------
# Layouts: every role has more than one arrangement
# --------------------------------------------------------------------------
# A single fixed arrangement per role made a long episode look like the same
# frame repeated.  Each role now has several **layouts**, and two consecutive
# scenes never get the same one.
LAYOUTS: dict[str, dict[str, dict[str, list[float]]]] = {
    "hook": {
        # a: the title high, the subtitle under it
        "a": {
            "title": [130, 220, 2300, 700],
            "sub": [190, 940, 2180, 340],
            "band": [150, 300, 2240, 340],
        },
        # b: a lower, wider title with the subtitle tucked under it
        "b": {
            "title": [230, 520, 2100, 500],
            "sub": [300, 1080, 1960, 300],
            "band": [220, 600, 2120, 360],
        },
        # c: a compact title with a narrow subtitle (a chapter card)
        "c": {
            "title": [130, 240, 2300, 560],
            "sub": [520, 840, 1520, 280],
            "band": [150, 280, 2240, 300],
        },
    },
    "evidence": {
        # a: the picture on the left, the caption on the right
        "a": {
            "image": [110, 330, 1400, 950],
            "strip": [1420, 130, 1030, 250],
            "label": [1450, 140, 980, 170],
            "caption": [1520, 400, 920, 740],
        },
        # b: the picture on the right, the caption on the left
        "b": {
            "image": [1050, 330, 1400, 950],
            "strip": [130, 130, 1030, 250],
            "label": [160, 140, 980, 170],
            "caption": [130, 400, 880, 740],
        },
        # c: a full-width picture with the caption underneath it
        "c": {
            "image": [130, 300, 2300, 820],
            "strip": [1660, 1160, 780, 220],
            "label": [1690, 1170, 720, 160],
            "caption": [130, 1180, 1440, 260],
        },
    },
    "explain": {
        # a: a big statement, a quieter detail line, a rule under them, and a
        #    character on the right that reacts to the idea
        "a": {
            "statement": [200, 470, 1600, 520],
            "detail": [200, 1030, 1600, 220],
            "rule": [200, 1240, 1600, 160],
            "figure": [1880, 430, 480, 760],
        },
        # b: the character on the left, the text on the right
        "b": {
            "statement": [820, 470, 1540, 520],
            "detail": [820, 1030, 1540, 220],
            "rule": [820, 1240, 1540, 160],
            "figure": [200, 430, 480, 760],
        },
        # c: a low statement with the rule at the foot of the page
        "c": {
            "statement": [200, 540, 1600, 480],
            "detail": [200, 1060, 1600, 200],
            "rule": [200, 1260, 1600, 140],
            "figure": [1880, 480, 460, 700],
        },
    },
    "close": {
        "a": {
            "statement": [200, 470, 1600, 520],
            "band": [200, 400, 1600, 340],
            "rule": [200, 1240, 1600, 160],
            "figure": [1880, 430, 480, 760],
        },
        "b": {
            "statement": [820, 470, 1540, 520],
            "band": [820, 400, 1540, 320],
            "rule": [820, 1240, 1540, 160],
            "figure": [200, 430, 480, 760],
        },
    },
}

VARIANTS: dict[str, tuple[str, ...]] = {
    role: tuple(sorted(variants)) for role, variants in LAYOUTS.items()
}


def _layout(role: str, variant: str) -> dict[str, list[float]]:
    """The geometry of one layout (with a safe fallback)."""
    layouts = LAYOUTS.get(role) or LAYOUTS["explain"]
    return layouts.get(variant) or next(iter(layouts.values()))


def _variant_for(role: str, index: int, text: str, previous: str | None) -> str:
    """Which layout a scene uses: deterministic, and never the same twice."""
    variants = VARIANTS.get(role) or ("a",)
    if len(variants) == 1:
        return variants[0]
    seed = (index * 31 + sum(ord(c) for c in (text or ""))) % len(variants)
    variant = variants[seed]
    if previous and variant == previous:
        position = variants.index(variant)
        variant = variants[(position + 1) % len(variants)]
    return variant


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
    rect = list(place["rect"])
    # the text is wrapped by **measured width** so it never runs out of its box,
    # and shortened when it would be drawn too small to read
    body = _fit_text(
        text,
        font_name=font,
        size=size,
        box_w=float(rect[2]),
        box_h=float(rect[3]),
    )
    return {
        "type": "text",
        "text": body or _wrap(text, wrap),
        "font": font,
        "size": size,
        "rect": rect,
        "mode": "skeleton",
        "rtl": not english,
        **({"weight": int(place["weight"])} if english else {}),
        "color": place["color"],
        "gap": 0.3,
    }


def _relevance_gate(project_dir: Path | None, enabled: bool | None = None):
    """بوابة الملاءمة — تُفتح افتراضيًّا إلا إذا عُطِّلت صراحةً.

    المنطق: البحث يجد **بالاسم**، فقد يُرجع صورة لا تمثّل المشهد (سفينة حديثة
    لقائد من القرن السادس عشر). الأصل الذي تحكم البوابة «غير ذي صلة» **لا
    يدخل الخطة**؛ والأصل «يحتاج عينًا» يدخل ويُعلَّم (البوابة البشرية
    ما زالت الفيصل).
    """
    if enabled is None:
        try:
            from ..core.config import load_config

            enabled = bool(load_config().get("research", "relevance_gate", default=True))
        except Exception:
            enabled = True
    if not enabled:
        return None
    try:
        from ..research.relevance import RelevanceGate

        return RelevanceGate()
    except Exception:
        return None


def _pick_visual(
    assets: list[dict],
    scene_text: str,
    gate,
    *,
    names: list[str],
) -> tuple[dict | None, list[dict]]:
    """اختيار صورة المشهد: أول أصل **غير مرفوض بالملاءمة**.

    يعيد (الأصل المختار، سجل الأحكام) — والسجل يُكتب في الخطة ليقرأه
    المحرّر: أي أصل رُفض بسببه، وأيّها «يحتاج عينًا».
    """
    if not assets:
        return None, []
    notes: list[dict] = []
    ordered = [a for a in assets if not a["vector"]] + [a for a in assets if a["vector"]]
    for asset in ordered:
        if gate is None:
            return asset, notes
        context = {
            "name": str(asset.get("entity") or (names[0] if names else "")),
            "type": str(asset.get("entity_type") or ""),
            "need": str(asset.get("need") or ""),
            "scene": scene_text,
        }
        verdict = gate.judge(
            {
                "id": asset.get("path"),
                "title": asset.get("title"),
                "mime": asset.get("mime"),
                "type": asset.get("need"),
            },
            context,
        )
        notes.append(
            {
                "path": asset.get("path"),
                "title": asset.get("title"),
                "verdict": verdict.verdict,
                "score": verdict.score,
                "reason": verdict.reason,
            }
        )
        if verdict.verdict == "irrelevant":
            continue
        return asset, notes
    return None, notes


def build_plan(
    graph: dict,
    research: dict,
    *,
    project_dir: Path | None = None,
    max_scenes: int | None = None,
    fps: FrameRate | int | float | str | dict | None = None,
    family: str | None = None,
    relevance: bool | None = None,
) -> dict:
    base = Path(project_dir) if project_dir else Path(".")
    # قاعدة زمن واحدة: المشروع يحدد المعدل، والافتراضي 24 (لا 30 ثابتة).
    rate = coerce_frame_rate(fps) if fps is not None else FrameRate(24)
    fam = get_family(family)
    index = _index_assets(research, _rejected_asset_paths(base))
    rejection_report = _apply_rejection_rules(index, base)
    gate = _relevance_gate(base, relevance)
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

    def _capacity_for(duration: float) -> int:
        """How many words can be **drawn** inside a scene of this length.

        Measured budget: 0.95 drawn words per second (106.92s of natural
        drawing against a 79.875s film on the production plan).  The formula
        is the same one the text budget uses, so the two always agree.
        """
        return max(1, int(float(duration) * NATURAL_DRAWN_WORDS_PER_SECOND))

    def _scene_elements(
        s: dict,
        i: int,
        role: str,
        recipe: tuple[str, ...],
        names: list[str],
        assets: list[dict],
        visual: dict | None,
        capacity: int,
        variant: str = "a",
    ) -> list[dict]:
        """Builds the elements of one scene for a given drawing capacity."""
        narration = (s.get("narration") or "").strip()
        elements: list[dict] = []
        lay = _layout(role, variant)
        text_chunks = _scene_text_chunks(role, graph, narration, visual, names, capacity)
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
                    has_visual=bool(visual),
                    variant=variant,
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
                # The band follows the **measured** width of the text it sits
                # behind: a fixed band left the last words of a long title
                # outside the highlight.
                title_chunk = text_chunks[0] if text_chunks else ""
                title_font_name = title_font if text_index == 0 else body_font
                band = _band_for(
                    title_chunk,
                    font_name=title_font_name,
                    size=title_size if role == "hook" else headline_size,
                    base=list(lay.get("band") or [150, 300, 2240, 340]),
                )
                elements.append(
                    {
                        "type": "highlight",
                        "rect": band,
                        "color": "#F3D57C",
                        "speed": 2.2,
                        "events": False,
                        "gap": 0.14,
                    }
                )
            elif kind == "underline":
                # the underline template draws at rect.y + rect.h + offset;
                # the rule rect of the layout keeps the stroke below the words
                # instead of striking through them.
                rect = list(lay.get("rule") or [130, 724, 2300, 380])
                if role == "hook":
                    # the hook's rule sits at the foot of the page (and inside
                    # the canvas: the explainer family draws it first)
                    rect = [130, 1290, 2300, 120]
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
            elif kind == "figure":
                # a character drawn with the pen; its pose follows the meaning
                figure_rect = list(lay.get("figure") or [1880, 430, 480, 760])
                elements.append(
                    {
                        "type": "figure",
                        "pose": _figure_pose(narration, role),
                        "rect": figure_rect,
                        "color": INK,
                        "gap": 0.45,
                    }
                )
            elif kind == "torn_strip":
                label = (visual.get("entity") if visual else None) or (names[0] if names else "")
                elements.append(
                    {
                        "type": "torn_strip",
                        "rect": list(lay.get("strip") or [1420, 130, 1030, 250]),
                        "seed": 21,
                        "tilt": -0.6,
                        "gap": 0.12,
                        **({"text": label, "font": body_font, "size": label_size} if label else {}),
                    }
                )
            elif kind in ("image", "svg"):
                if not visual:
                    continue
                visual_rect = list(lay.get("image") or [110, 330, 1400, 950])
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
                        place={"rect": [1450, 150, 980, 190], "color": ACCENT, "weight": 500},
                        wrap=3,
                    ),
                )

        return elements

    context: list[tuple] = []
    relevance_notes: list[dict] = []
    # --- pass 1: what does each scene have? (names, assets, a picture) ---
    prepared: list[dict] = []
    for i, s in enumerate(scenes, 1):
        names = _scene_entities(s, index)
        assets: list[dict] = []
        for n in names:
            assets += index.get(n, [])
        visual, notes = _pick_visual(
            assets, str(s.get("narration") or ""), gate, names=names
        )
        for note in notes:
            relevance_notes.append({"scene": s.get("id", i), **note})
        if not fam.allows_images:
            visual = None
        prepared.append({"i": i, "s": s, "names": names, "assets": assets, "visual": visual})

    # --- pass 2: the role of every scene comes from its **content** ---
    roles = resolve_roles(
        [p["s"] for p in prepared],
        has_visual=[bool(p["visual"]) for p in prepared],
    )

    # --- pass 3: build the elements ---
    previous_variant: str | None = None
    for pos, p in enumerate(prepared):
        i, s = p["i"], p["s"]
        names, assets, visual = p["names"], p["assets"], p["visual"]
        role = roles[pos]
        recipe = fam.recipe.get(role) or fam.recipe.get("explain", ())
        narration = (s.get("narration") or "").strip()
        duration = float(s.get("duration") or 6.0)
        variant = _variant_for(role, i, narration, previous_variant)
        previous_variant = variant
        elements = _scene_elements(
            s, i, role, recipe, names, assets, visual, _capacity_for(duration), variant
        )
        context.append((s, i, role, recipe, names, assets, visual, variant))
        # "used" means **drawn**: an asset that merely matched the scene text
        # but was not placed in any element is not used, and must not be
        # credited or gated as if it were.
        drawn_visual = (
            visual
            if visual and any(el.get("type") in ("image", "svg") for el in elements)
            else None
        )
        out_scenes.append(
            {
                "id": s.get("id", i),
                "duration": duration,
                "narration": narration,
                "role": role,
                "layout": variant,
                "needs": s.get("needs", []),
                "assets_used": [drawn_visual["path"]] if drawn_visual else [],
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

    # ميزانية الرسم: النص **المرسوم على الشاشة** يجب أن يُرسم ضمن مدة المشهد.
    # تُحسب **بعد** تطبيق المحاذاة، لأن المدة التي ستُرسم فعلًا هي مدة الصوت
    # لا تقدير الكلمات/الثانية.  المعامل مقيس على خطة الإنتاج: ~0.95 كلمة
    # مرسومة في الثانية (106.92ث رسم طبيعي مقابل 79.875ث فيلم).
    #
    # ولأن المدة النهائية معروفة الآن، يُعاد بناء عناصر النص بسعة المشهد
    # الحقيقية: مشهد قصير يحصل على تعليق أقصر بدل تعليق لا يُرسم في وقته.
    for idx, sc in enumerate(out_scenes):
        s, i, role, recipe, names, assets, visual, variant = context[idx]
        sc["elements"] = _scene_elements(
            s, i, role, recipe, names, assets, visual, _capacity_for(sc["duration"]), variant
        )

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
        "relevance": {
            "gate": bool(gate),
            "judged": len(relevance_notes),
            "rejected": sum(1 for r in relevance_notes if r.get("verdict") == "irrelevant"),
            "needs_human": sum(1 for r in relevance_notes if r.get("verdict") == "uncertain"),
            "items": relevance_notes[:80],
        },
        "rejections": {
            "rules": rejection_report.get("rules", 0),
            "blocked": rejection_report.get("blocked", [])[:40],
        },
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
