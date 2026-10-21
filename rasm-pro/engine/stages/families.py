"""Template families and motion rules — Stage 6.

A **family** is a named way of building a scene: which elements appear, where
they sit, how much text a scene may carry, and how the camera behaves while
they are drawn.  Three families, no more — each one earns its place by being
visibly different and by solving a different kind of scene:

``documentary``
    Photo-led: a torn strip, the evidence image, a label and a caption.
    For history and evidence. Light text, so the drawing fits the clock.

``explainer``
    Text-led: a headline, an underline or a highlight. No photos, so it
    draws fast and stays readable — the safest family for a fixed narration.

``dense``
    Information-led: a headline plus a timeline or bars, with a small
    evidence image. For scenes that carry a sequence or a number.

The motion profile is data, not scattered constants: the renderer reads it to
decide how the camera frames each element type.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "FAMILIES",
    "Family",
    "MotionProfile",
    "SCENE_ROLES",
    "get_family",
    "list_families",
    "scene_role",
    "text_budget",
]

# The role of a scene inside an episode, decided by its content.
SCENE_ROLES = ("hook", "evidence", "explain", "close")

# Words that mark a scene as a question, a claim, or a closing call.
QUESTION_WORDS = ("?", "who", "what", "why", "how", "when", "where", "which")
CONCLUSION_WORDS = (
    "start",
    "begin",
    "write",
    "remember",
    "try",
    "now",
    "today",
    "finally",
    "remember this",
    "so start",
)


def scene_role(index: int, total: int) -> str:
    """The role of scene ``index`` (1-based) inside an episode of ``total``.

    Kept for compatibility: the *position* based fallback.  New plans use
    :func:`resolve_roles`, which decides from the content.
    """
    if index == 1:
        return "hook"
    if index == total:
        return "close"
    if index % 3 == 0:
        return "explain"
    return "evidence"


def _is_question(text: str) -> bool:
    low = " ".join((text or "").lower().split())
    if not low:
        return False
    if low.endswith("?") or "?" in low:
        return True
    first = low.split()[0] if low.split() else ""
    return first in QUESTION_WORDS


def _is_conclusion(text: str) -> bool:
    low = " ".join((text or "").lower().split())
    if not low:
        return False
    return any(w in low for w in CONCLUSION_WORDS)


def resolve_roles(
    scenes: list[dict],
    *,
    has_visual: list[bool] | None = None,
) -> list[str]:
    """Decide the role of every scene from **its content**, not its number.

    The old rule (first = hook, every third = explain, last = close) meant
    that a scene with a real source could land on ``explain`` — a role with
    no image slot — and the author had to reorder the script by hand to make
    the pictures fit.  Now:

    * an explicit ``role`` on the scene always wins;
    * the first scene is a ``hook`` when it asks something, else it opens
      the episode (still a hook: it is the first thing the viewer sees);
    * a scene that carries a **source picture** is ``evidence``;
    * the last scene is a ``close`` when it calls for action, else ``explain``;
    * everything else is ``explain``.

    The result is a list of roles, one per scene.
    """
    total = len(scenes)
    roles: list[str] = []
    for index, scene in enumerate(scenes):
        explicit = str((scene or {}).get("role") or "").strip().lower()
        if explicit in SCENE_ROLES:
            roles.append(explicit)
            continue
        text = str((scene or {}).get("narration") or "")
        visual = bool(has_visual[index]) if has_visual and index < len(has_visual) else False
        if index == 0:
            roles.append("hook")
            continue
        if index == total - 1:
            # a call to action ends the episode; a picture in the last scene
            # is evidence (it must be drawn); anything else is a closing card
            if _is_conclusion(text) or not visual:
                roles.append("close")
            else:
                roles.append("evidence")
            continue
        if visual:
            roles.append("evidence")
            continue
        if _is_question(text) and index <= 1:
            roles.append("hook")
            continue
        roles.append("explain")
    return roles


@dataclass(frozen=True)
class MotionProfile:
    """How the camera behaves for a family (read by the renderer)."""

    # zoom factor applied to the active element's bounding box
    zoom: float = 2.6
    # camera smoothing per frame (lower = snappier follow)
    follow: float = 0.07
    # per element-type zoom overrides; 1.0 = keep the current frame
    zoom_by_type: dict[str, float] = field(default_factory=dict)
    # hold the camera still while a text element is written (readability)
    hold_on_text: bool = False
    # seconds of the scene spent showing the whole canvas before the first
    # element starts (a breath, not a black frame)
    lead_in: float = 0.0


@dataclass(frozen=True)
class Family:
    """A named template family."""

    name: str
    description: str
    languages: tuple[str, ...]
    # maximum words a scene may carry (the drawing has to fit the clock)
    words_per_scene: int
    # which element types the family may use
    allows_images: bool = True
    motion: MotionProfile = field(default_factory=MotionProfile)
    # per role: which element types appear, in order
    recipe: dict[str, tuple[str, ...]] = field(default_factory=dict)


# --------------------------------------------------------------------------
# the three families
# --------------------------------------------------------------------------
DOCUMENTARY = Family(
    name="documentary",
    description="صور وشواهد: شريط ممزق + صورة + عنوان + تعليق",
    languages=("ar", "en"),
    words_per_scene=16,
    allows_images=True,
    motion=MotionProfile(
        zoom=2.8,
        follow=0.06,
        zoom_by_type={"image": 2.4, "svg": 2.4, "torn_strip": 1.6, "paper_card": 1.8},
        hold_on_text=False,
        lead_in=0.15,
    ),
    recipe={
        "hook": ("highlight", "text", "text"),
        "evidence": ("torn_strip", "text", "image", "text"),
        # a statement + a quieter detail line + a rule under them
        "explain": ("text", "text", "underline"),
        "close": ("highlight", "text", "underline"),
    },
)

EXPLAINER = Family(
    name="explainer",
    description="نصّي: عنوان كبير + تسطير/تظليل — يُرسم أسرع وأسهل قراءة",
    languages=("ar", "en"),
    words_per_scene=12,
    allows_images=False,
    motion=MotionProfile(
        zoom=1.9,
        follow=0.08,
        zoom_by_type={"text": 1.6, "underline": 1.4, "highlight": 1.4},
        hold_on_text=True,
        lead_in=0.1,
    ),
    recipe={
        "hook": ("underline", "text", "text"),
        "evidence": ("text", "flourish", "text"),
        "explain": ("text", "underline", "text"),
        "close": ("text", "underline", "text", "flourish"),
    },
)

DENSE = Family(
    name="dense",
    description="معلومة كثيفة: عنوان + خط زمني/أعمدة + صورة صغيرة",
    languages=("ar", "en"),
    words_per_scene=20,
    allows_images=True,
    motion=MotionProfile(
        zoom=2.2,
        follow=0.07,
        zoom_by_type={"timeline": 1.2, "bars": 1.2, "image": 2.0, "text": 1.5},
        hold_on_text=False,
        lead_in=0.12,
    ),
    recipe={
        "hook": ("flourish", "text", "text"),
        "evidence": ("text", "image", "text"),
        "explain": ("text", "timeline", "text"),
        "close": ("text", "bars", "underline"),
    },
)

FAMILIES: dict[str, Family] = {
    f.name: f for f in (DOCUMENTARY, EXPLAINER, DENSE)
}
DEFAULT_FAMILY = DOCUMENTARY.name


def list_families() -> list[dict[str, Any]]:
    return [
        {
            "name": f.name,
            "description": f.description,
            "languages": list(f.languages),
            "words_per_scene": f.words_per_scene,
            "allows_images": f.allows_images,
            "recipe": {role: list(types) for role, types in f.recipe.items()},
            "motion": {
                "zoom": f.motion.zoom,
                "follow": f.motion.follow,
                "zoom_by_type": dict(f.motion.zoom_by_type),
                "hold_on_text": f.motion.hold_on_text,
                "lead_in": f.motion.lead_in,
            },
        }
        for f in FAMILIES.values()
    ]


def get_family(name: str | None) -> Family:
    key = str(name or DEFAULT_FAMILY).strip().lower()
    if key not in FAMILIES:
        raise ValueError(
            f"عائلة غير معروفة: {key!r} (المتاحة: {', '.join(sorted(FAMILIES))})"
        )
    return FAMILIES[key]


def text_budget(family: Family) -> int:
    """Maximum words a scene of this family may carry."""
    return int(family.words_per_scene)
