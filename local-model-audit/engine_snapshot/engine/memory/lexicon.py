"""ذاكرة التعلّم: قواعد مدمجة + تصحيحات متراكمة تُطبَّق على الفهم والبحث.

الفكرة: أي خطأ يتكرر (اسم شائع يُطابق كيانًا خاطئًا، نوع كيان غلط، كلمة بحث
ضعيفة) يُصلَح مرة واحدة ويُخزَّن هنا، فيستفيد منه كل تشغيل قادم — بلا إعادة
تدريب نموذج وبلا صيانة يدوية.

ملف التصحيحات: ``memory/corrections.jsonl`` — سطر JSON لكل تصحيح:
    {"kind": "alias"|"type"|"needs", "key": "...", "value": ..., "note": "...", "added": "..."}
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from ..core.paths import ROOT

MEM_DIR = ROOT / "memory"
MEM_FILE = MEM_DIR / "corrections.jsonl"

# ————— قواعد مدمجة (دروس تشخيصية من تشغيل حقيقي) —————

# أسماء شائعة في السكريبت العربي → الاسم المرجعي الأدق للبحث
DEFAULT_ALIASES: dict[str, str] = {
    "بريطانيا": "المملكة المتحدة",
    "بريطانيا العظمى": "المملكة المتحدة",
    "إنجلترا": "المملكة المتحدة",
    "انجلترا": "المملكة المتحدة",
    "أمريكا": "الولايات المتحدة",
    "امريكا": "الولايات المتحدة",
    "إنجلترا وبريطانيا": "المملكة المتحدة",
}

# كلمات تكشف أن نتيجة المطابقة «عمل فني/إعلامي» وليست الكيان المقصود
WORK_START_AR = (
    "فيلم", "مسلسل", "ألبوم", "أغنية", "رواية", "لعبة", "برنامج", "أنمي", "مانغا",
    "مسرحية", "عمل درامي", "قصة مصورة", "أوبريت",
)
WORK_PHRASE_AR = (
    "هو فيلم", "هي فيلم", "هو مسلسل", "هي مسلسل", "هو ألبوم", "هو برنامج",
    "فيلم أنتج", "فيلم من إنتاج", "تم إنتاجه في سنة", "تم عرضه في سنة",
)
WORK_WORD_EN = (
    "film", "movie", "tv series", "television series", "album", "song", "novel",
    "video game", "manga", "anime", "opera", "sitcom",
)
# مهن تجعل «film director» وصفًا لشخص لا لعمل
_PERSON_ROLE_EN = ("director", "producer", "critic", "actor", "actress", "composer", "scholar", "historian", "writer", "editor", "festival")


def looks_like_work(description: str) -> bool:
    """هل وصف الكيان يدل على عمل فني/إعلامي (فيلم/مسلسل/ألبوم...)؟"""
    d = (description or "").strip()
    if not d:
        return False
    low = d.lower()
    for w in WORK_START_AR:
        if d.startswith(w):
            return True
    for p in WORK_PHRASE_AR:
        if p in d:
            return True
    for w in WORK_WORD_EN:
        idx = low.find(w)
        if idx < 0:
            continue
        # فيلم/مسلسل: غالبًا في البداية (مع سنة اختيارية) أو بصيغة "هو/هي ..."
        head = low[: idx].strip()
        head_words = [t for t in head.replace("-", " ").split() if t]
        if len(head_words) <= 4 and all(t.isdigit() or t.isalpha() or t in ("a", "an", "the") for t in head_words):
            after = low[idx + len(w) : idx + len(w) + 18]
            if any(r in after for r in _PERSON_ROLE_EN):
                continue  # "film director" = شخص
            return True
        if any(f" هو {w}" in low or f" هي {w}" in low or f" is a {w}" in low for w in (w,)):
            return True
    return False


# ————— التصحيحات —————


@dataclass
class Lexicon:
    aliases: dict[str, str] = field(default_factory=dict)
    type_fixes: dict[str, str] = field(default_factory=dict)
    needs_fixes: dict[str, list[str]] = field(default_factory=dict)
    notes: dict[str, str] = field(default_factory=dict)

    @staticmethod
    def load(path: Path | None = None) -> "Lexicon":
        lex = Lexicon(aliases=dict(DEFAULT_ALIASES))
        p = Path(path) if path else MEM_FILE
        if not p.exists():
            return lex
        try:
            lines = p.read_text(encoding="utf-8").splitlines()
        except Exception:
            return lex
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue  # سطر تالف لا يُسقط الذاكرة
            kind = rec.get("kind")
            key = str(rec.get("key") or "").strip()
            if not kind or not key:
                continue
            if kind == "alias":
                lex.aliases[key] = str(rec.get("value") or "").strip()
            elif kind == "type":
                lex.type_fixes[key] = str(rec.get("value") or "").strip()
            elif kind == "needs":
                v = rec.get("value")
                if isinstance(v, str):
                    v = [v]
                if isinstance(v, list):
                    lex.needs_fixes[key] = [str(x) for x in v]
            if rec.get("note"):
                lex.notes[key] = str(rec["note"])
        return lex

    # ————— استعلامات —————
    def alias(self, name: str) -> str | None:
        n = (name or "").strip()
        return self.aliases.get(n)

    def type_fix(self, name: str) -> str | None:
        return self.type_fixes.get((name or "").strip())

    def needs_fix(self, name: str) -> list[str] | None:
        return self.needs_fixes.get((name or "").strip())


def add_correction(kind: str, key: str, value, *, note: str = "", path: Path | None = None) -> Path:
    """يضيف تصحيحًا للذاكرة (append آمن) ويرجعه على القرص."""
    if kind not in ("alias", "type", "needs"):
        raise ValueError(f"نوع تصحيح غير معروف: {kind}")
    p = Path(path) if path else MEM_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    rec = {
        "kind": kind,
        "key": str(key).strip(),
        "value": value,
        "note": note,
        "added": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return p


def is_generic_collective(name: str) -> bool:
    """اسم جمع/عام (الجنود، المدنيون، القوات) — لا يُطابق كشخص بعينه."""
    n = (name or "").strip()
    if not n or " " in n:
        return False
    core = n[2:] if n.startswith("ال") else n
    if len(core) < 3:
        return False
    if core.endswith(("ون", "ين", "ات")):
        return True
    broken_plurals = {"جنود", "قوات", "جيوش", "مدن", "دول", "ضحايا", "معارك", "حروب", "أسلحة", "جيوش", "مقاتلون"}
    return core in broken_plurals
