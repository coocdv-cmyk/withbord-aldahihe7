"""كتابة السكريبت من **فكرة موضوع** — بالموديل المحلي، وبعقد صارم.

الفكرة تُعطى للموديل، والموديل يُعيد *مسودّة مشاهد*، والمحرّك يتحقّق منها
ويصلح ما يمكن إصلاحه.  القواعد:

* **عقد صارم**: JSON فقط، قائمة مشاهد، كل مشهد نصٌّ واحد.
* **لا ادّعاء بلا مصدر**: يُطلب من الموديل أخطاءً عامة (Facts) لا أسماء
  وأرقامًا خاصة (Facts) — وكل ادّعاء يمرّ على بوابة البحث لاحقًا.
* **السرعة**: نداءٌ واحد، موديل محلي 4B، مهلة قصيرة، ودرجة حرارة منخفضة.
* **الاحتياطي الحتمي**: إن لم يستجب الموديل، يبني المحرّك هيكلًا من
  الموضوع (ويقول صراحةً إن المسودّة حتمية لا موديل).

الأولوية للموديل **المحلي الخفيف**: `providers.llm` يفضّل المحلي أولًا
ولا ينزل إلى مُدفوع إلا بطلب صريح.
"""
from __future__ import annotations

import json
import re
from typing import Any

from ..core import arabic
from ..core.log import get_logger
from ..providers.llm import LLM, LLMError

log = get_logger("stages.script")

SYSTEM_PROMPT = (
    "أنت كاتب سكريبت لفيديو وايت بورد تعليمي. "
    "أجب بـ JSON فقط، بلا أي نص آخر.\n"
    "العقد: {\"scenes\": [{\"text\": \"...\"}]}\n"
    "قواعد:\n"
    "1) كل مشهد جملة أو جملتان، 12-25 كلمة، بلغة بسيطة.\n"
    "2) المشهد الأول سؤال أو ادّعاء يوقّف المشاهد؛ المشهد الأخير خلاصة عملية.\n"
    "3) تجنّب الأسماء الخاصة والأرقام والتواريخ غير المؤكدة — عمّم ما يمكن.\n"
    "4) كل مشهد فكرة واحدة مستقلة، والدوال بين المشاهد تترجم المعنى لا الكلمات.\n"
    "5) لا تكرّر ولا تشرح ما تشرحه الجملة السابقة."
)

USER_TEMPLATE = """الموضوع: {topic}

اكتب {scenes} مشاهد بالترتيب، كل مشهد فكرة واحدة. أول مشهد سؤال أو ادّعاء يوقّف، وآخر مشهد خلاصة عملية قابلة للتنفيذ."""


class ScriptError(RuntimeError):
    """تعذّر إنتاج سكريبت صالح."""


def _clean(text: str) -> str:
    return " ".join(str(text or "").replace('"', " ").split())


def validate_scenes(raw: Any, *, min_words: int = 8, max_words: int = 32) -> list[dict]:
    """يتحقّق من مسودّة الموديل ويصلح ما يمكن: مشاهد بطول قابل للرسم."""
    if isinstance(raw, dict):
        raw = raw.get("scenes") or raw.get("scene") or []
    if not isinstance(raw, list) or not raw:
        raise ScriptError("the model did not return a list of scenes")
    out: list[dict] = []
    for item in raw:
        if isinstance(item, str):
            text = _clean(item)
        elif isinstance(item, dict):
            text = _clean(item.get("text") or item.get("narration") or item.get("line") or "")
        else:
            continue
        if not text:
            continue
        words = text.split()
        if len(words) > max_words:
            text = " ".join(words[:max_words]) + "…"
        elif len(words) < min_words:
            # a too-short scene cannot carry a caption: keep it but mark it
            text = text
        out.append({"text": text, "words": len(text.split())})
    if not out:
        raise ScriptError("the model returned no usable scene")
    return _merge_short_scenes(out, min_words=min_words)


def _merge_short_scenes(scenes: list[dict], *, min_words: int = 8) -> list[dict]:
    """A scene shorter than the minimum is merged with the next one.

    The model often writes seven-word lines; a whiteboard needs a line that can
    carry a caption, so two short lines become one scene.  The two are joined
    **as two sentences** (". ") so the result still reads as prose.
    """
    def _join(left: str, right: str) -> str:
        left = left.rstrip(" .،,")
        right = right.lstrip(" .،,")
        return f"{left}. {right}" if left and right else (left or right)

    merged: list[dict] = []
    for scene in scenes:
        if merged and merged[-1]["words"] < min_words:
            previous = merged[-1]
            previous["text"] = _join(previous["text"], scene["text"])
            previous["words"] = len(previous["text"].split())
            continue
        merged.append(dict(scene))
    # a short tail is merged backwards
    while len(merged) > 1 and merged[-1]["words"] < min_words:
        tail = merged.pop()
        merged[-1]["text"] = _join(merged[-1]["text"], tail["text"])
        merged[-1]["words"] = len(merged[-1]["text"].split())
    return merged


def fallback_scenes(topic: str, scenes: int = 10) -> list[dict]:
    """هيكل حتمي بلا موديل (احتياطي صريح)."""
    topic = _clean(topic) or "الموضوع"
    seeds = [
        f"ما الذي يحدث فعلًا في {topic} ولماذا يهمنا ذلك الآن؟",
        f"لماذا يبدو {topic} أبسط مما هو في الواقع؟",
        f"أول جزء من الحكاية عن {topic} يبدأ قبل أن نتوقعه.",
        f"ثم يأتي السؤال الأهم عن {topic}، وهو ليس تقنيًا.",
        f"والتفصيل الأول الذي يفيدك فعلًا في {topic} بسيط.",
        f"وهنا تخطئ أغلب الناس في {topic} دون أن ينتبهوا.",
        f"ما الذي يغيّر النتيجة حقًا في {topic}؟ ثلاثة أشياء.",
        f"القاعدة العملية في {topic} واضحة، ومجرَّبة، وسهلة التطبيق.",
        f"وماذا يعني ذلك لك اليوم عمليًا، خطوة واحدة؟",
        f"ابدأ الآن: خطوة واحدة في {topic}، ثم قِس أثرها بعد أسبوع.",
    ]
    out = []
    for index in range(max(1, scenes)):
        text = seeds[index % len(seeds)]
        out.append({"text": text, "words": len(text.split())})
    return out


def write_script(
    topic: str,
    *,
    scenes: int = 10,
    language: str = "ar",
    llm: LLM | None = None,
    timeout_s: int = 180,
) -> dict:
    """ideka → مسودّة مشاهد. تعيد المسودّة + كيف أُنتجت (موديل/حتمي)."""
    client = llm or LLM()
    mode = "fallback"
    raw = None
    error = ""
    if client.available:
        try:
            raw = client.ask_json(
                SYSTEM_PROMPT,
                USER_TEMPLATE.format(topic=topic, scenes=scenes),
                temperature=0.2,
                retries=1,
            )
            mode = f"llm:{client.backend()}"
        except LLMError as exc:
            error = str(exc)
            log.warning("the model did not answer (%s) — the deterministic outline is used", exc)
    else:
        error = "no model reachable"
    if raw is None:
        return {
            "scenes": fallback_scenes(topic, scenes),
            "mode": "fallback",
            "reason": error,
            "language": language,
        }
    try:
        parsed = validate_scenes(raw, min_words=16)
    except ScriptError as exc:
        return {
            "scenes": fallback_scenes(topic, scenes),
            "mode": "fallback",
            "reason": f"{exc}: {error}",
            "language": language,
        }
    return {
        "scenes": parsed,
        "mode": mode,
        "reason": error,
        "language": language,
    }


def script_to_graph(result: dict, *, hook: str = "") -> dict:
    """يحوّل المسودّة إلى ScriptGraph (بالمشاهد والدور والمدة)."""
    scenes = []
    for index, item in enumerate(result.get("scenes") or [], 1):
        words = int(item.get("words") or len(str(item.get("text") or "").split()))
        scenes.append(
            {
                "id": index,
                "narration": str(item.get("text") or "").strip(),
                "duration": round(max(4.0, words / 2.45), 2),
                "needs": [],
                "keywords": [k for k, _ in arabic.keywords(str(item.get("text") or ""), top=4)],
            }
        )
    first = scenes[0]["narration"] if scenes else ""
    return {
        "engine": f"script:{result.get('mode')}",
        "lang": result.get("language") or ("ar" if arabic.is_arabic(first) else "en"),
        "tone": "وثائقي",
        "audience": "عام",
        "hook": hook or (first[:120] if first else ""),
        "claims": [],
        "entities": [],
        "timeline": [],
        "quotes": [],
        "numbers": [],
        "scenes": scenes,
        "stats": {
            "words": sum(s["duration"] and 0 or 0 for s in scenes),
            "sentences": len(scenes),
        },
    }
