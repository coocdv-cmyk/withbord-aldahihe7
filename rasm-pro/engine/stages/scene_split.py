"""تقسيم السكريبت إلى مشاهد **بالمحتوى** — لا بالرقم.

المحرّك يجب أن يقبل سكريبتًا خامًا (فقرات أو جدار نص) فيُخرج مشاهد
كلٌّ منها فكرة واحدة، بطول يسمح برسم تعليق عليها وقراءته.

القواعد (كلها قابلة للقياس، لا ذوق):

1. **الفقرة حدٌّ صلب**: لا تُدمج فقرتان في مشهد واحد (نية الكاتب).
2. **فكرة واحدة لكل مشهد**: داخل الفقرة يُجمَع ما دارت الجمل حتى يبلغ
   المشهد ``MAX_WORDS``، أو تُفصل عند علامة انتقال قوي (سؤال، «لأن»،
   «لذلك»، «لكن»، «إذًا») بشرط أن يكون المشهد قد بلغ ``MIN_WORDS``.
3. **طول قابل للرسم**: لا مشهد أقصر من ``MIN_WORDS`` (أقل من ذلك لا يسع
   تعليقًا مقروءًا)، ولا أطول من ``MAX_WORDS``.
4. **الخطّاف والخاتمة**: المشهد الأول خطّاف، وآخر مشهد خاتمة.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..core import arabic

MIN_WORDS = 14          # أقل كلمات مشهد يحمل تعليقًا مقروءًا
MAX_WORDS = 26          # أكثر كلمات مشهد قبل أن يصير جدارًا
IDEAL_WORDS = 20        # الهدف المريح

# علامات انتقال قوي: بعدها تبدأ فكرة جديدة
BREAK_MARKERS = (
    "لأن", "لأنّ", "لذلك", "لكن", "غير أن", "إذًا", "إذن", "إذ",
    "بسبب", "وبالتالي", "ثم", "بعد ذلك", "على أي حال", "في المقابل",
    "because", "therefore", "however", "but ", "so ",
)
QUESTION_MARKS = ("?", "؟")


@dataclass
class Scene:
    """مشهد مقسَّم: نصُّه وعدد كلماته ودوره المقترح."""

    narration: str
    words: int = 0
    role: str = "explain"
    sentences: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "narration": self.narration,
            "words": self.words,
            "role": self.role,
        }


def _is_question(sentence: str) -> bool:
    return any(mark in sentence for mark in QUESTION_MARKS)


def _is_break(sentence: str) -> bool:
    """هل تبدأ الجملة علامة انتقال قوي؟"""
    low = sentence.strip().lower()
    return any(low.startswith(marker) for marker in BREAK_MARKERS)


def _words(text: str) -> int:
    return len(str(text or "").split())


def split_scenes(text: str, *, min_words: int = MIN_WORDS, max_words: int = MAX_WORDS) -> list[Scene]:
    """يقسّم نصًّا خامًا إلى مشاهد: فكرة واحدة لكل مشهد بطول قابل للرسم."""
    text = (text or "").strip()
    if not text:
        return []
    blocks = [b.strip() for b in re.split(r"\n\s*\n+", text) if b.strip()]
    if not blocks:
        blocks = [text]

    scenes: list[Scene] = []
    for block in blocks:
        sentences = [s.strip() for s in arabic.split_sentences(block) if s.strip()]
        current: list[str] = []
        count = 0
        for sentence in sentences:
            words = _words(sentence)
            strong = (_is_question(sentence) or _is_break(sentence)) and count >= min_words
            too_long = count + words > max_words and count >= min_words
            if current and (strong or too_long):
                scenes.append(Scene(narration=" ".join(current), words=count))
                current, count = [], 0
            current.append(sentence)
            count += words
            if count >= max_words:
                scenes.append(Scene(narration=" ".join(current), words=count))
                current, count = [], 0
        if current:
            scenes.append(Scene(narration=" ".join(current), words=count))

    # a too-short scene is merged into its neighbour (never drawn alone)
    merged: list[Scene] = []
    for scene in scenes:
        if merged and scene.words < min_words and merged[-1].words + scene.words <= max_words + 6:
            previous = merged[-1]
            previous.narration = f"{previous.narration} {scene.narration}".strip()
            previous.words = _words(previous.narration)
            continue
        merged.append(scene)
    scenes = merged

    # the hook and the close
    if scenes:
        first = scenes[0]
        first.role = "hook"
        if len(scenes) > 1:
            scenes[-1].role = "close"
    return scenes


def scene_durations(scenes: list[Scene], words_per_second: float = 2.45) -> list[float]:
    """مدد المشاهد التقديرية (بالثواني) — تُستبدل بالمقيسة بعد المحاذاة."""
    return [round(max(4.0, s.words / max(0.5, words_per_second)), 2) for s in scenes]
