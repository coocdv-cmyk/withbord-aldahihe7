"""فهم السكريبت → ScriptGraph: كيانات، ادّعاءات، خط زمني، مشاهد، احتياجات بصرية.

- مع LLM: تحليل دلالي كامل بعقد JSON صارم.
- بلا LLM: تحليل احتياطي بالأنماط (يفكّك مشاهد ويسجّل الكيانات الأولية).
"""
from __future__ import annotations

import re
from typing import Any

from ..core import arabic
from ..core.util import sha256_text, write_json
from ..memory.lexicon import Lexicon, is_generic_collective
from ..providers.llm import LLM, LLMError

_LEX: Lexicon | None = None


def _lexicon() -> Lexicon:
    """ذاكرة التعلّم (تُحمَّل مرة واحدة لكل عملية)."""
    global _LEX
    if _LEX is None:
        _LEX = Lexicon.load()
    return _LEX


def _apply_memory(name: str, etype: str, needs: list[str]) -> tuple[str, list[str]]:
    """يطبّق الذاكرة: نوع مُصحَّح، جمع عام → مفهوم، احتياجات مُصحَّحة.

    هذه هي «الخبرة المتراكمة»: كل تصحيح يُضاف للذاكرة يُصلح كل تشغيل قادم.
    """
    lex = _lexicon()
    fixed = lex.type_fix(name)
    if fixed:
        etype = fixed
    if etype == "person" and is_generic_collective(name):
        etype = "concept"
    nf = lex.needs_fix(name)
    if nf:
        needs = list(nf)
    if etype == "concept" and needs and all(n == "portrait" for n in needs):
        needs = ["object"]  # صورة عامة بدل بورتريه شخص
    return etype, list(dict.fromkeys(needs))[:6]

SCENE_WORDS_TARGET = 20          # كلمات مثالية لكل مشهد
WORDS_PER_SECOND = 2.45          # معدل إلقاء عربي تقديري
# أقل عدد كلمات justifies قطعَ مشهد بعد علامة استفهام: سؤال من 4 كلمات
# داخل فقرة هو بداية الجملة لا مشهد مستقل.
MIN_SCENE_WORDS = 8
# مشهد أقصر من هذا يُدمج في سابقه (مشهد من 3 كلمات لا يُرسم ولا يُقال).
MIN_MERGE_WORDS = 12
_PARAGRAPH_RE = re.compile(r"\n{2,}")

# كلمات دالة على نوع الكيان والاحتياج البصري
NEED_HINTS: dict[str, tuple[str, ...]] = {
    "portrait": ("ملك", "رئيس", "قائد", "زعيم", "قائد", "شخص", "عالم", "كاتب", "فيلسوف", "جنرال", "ديكتاتور", "إمبراطور", "خليفة", "سلطان", "أمير", "وزير", "مفكر", "صحفي", "فنان", "مخترع", "طبيب"),
    "event": ("حرب", "معركة", "ثورة", "غزو", "احتلال", "انقلاب", "مظاهرة", "مذبحة", "هجوم", "اتفاق", "معاهدة", "إعلان", "استقلال", "سقوط", "انهيار", "زلزال", "اكتشاف", "هجرة", "حصار", "مؤتمر"),
    "map": ("خريطة", "حدود", "منطقة", "إقليم", "مدينة", "عاصمة", "دولة", "بلاد", "جغرافيا", "أرض", "بحر", "نهر", "جبل", "صحراء"),
    "flag": ("علم", "دولة", "جمهورية", "مملكة", "اتحاد", "دولة", "راية"),
    "chart": ("نسبة", "إحصاء", "مليون", "مليار", "ألف", "٪", "%", "ارتفع", "انخفض", "تضخم", "اقتصاد", "دخل", "سكان", "عدد", "إحصائية", "رقم"),
    "document": ("وثيقة", "معاهدة", "قانون", "دستور", "خطاب", "رسالة", "تقرير", "عقد", "مخطوطة", "صحيفة", "جريدة"),
    "object": ("جهاز", "آلة", "اختراع", "سلاح", "صاروخ", "دبابة", "طائرة", "سفينة", "قطار", "سيارة", "هاتف", "كمبيوتر", "قنبلة", "بندقية"),
    "symbol": ("فكرة", "مفهوم", "رمز", "معنى", "دلالة", "قيمة", "مبدأ", "نظرية"),
    "portrait": ("ملك", "رئيس", "قائد", "زعيم", "شخص", "عالم", "كاتب", "فيلسوف", "جنرال", "إمبراطور", "خليفة", "سلطان", "أمير", "مفكر", "فنان", "مخترع"),
}

PERSON_RE = re.compile(
    r"\b(?:الملك|الملكة|الرئيس|الزعيم|القائد|الإمبراطور|السلطان|الخليفة|الأمير|الجنرال|الدكتور|المهندس|العالم|الكاتب|الفيلسوف|البابا|القائد)\s+([\u0600-\u06FF]{3,}(?:\s+[\u0600-\u06FF]{3,})?)"
)
CAPS_RE = re.compile(r"\b([A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,}){0,3})\b")


def estimate_duration(text: str) -> float:
    return max(5.0, arabic.word_count(text) / WORDS_PER_SECOND)


def heuristic_scenes(text: str) -> list[dict]:
    """يقسّم النص إلى مشاهد **دون أن يعبر فقرة الكاتب أبدًا**.

    الفقرة (سطر فارغ) هي نيّة الكاتب: لا يجوز أن يُدمج ما بعدها بما قبلها،
    ولا أن يُقطع جملة في نصفها.  داخل الفقرة تُجمَّع الجمل حتى بلوغ
    ``SCENE_WORDS_TARGET``، ويُقطع عند سؤال/تعجب فقط إذا اجتمع حوله عدد
    كلمات كافٍ.  وأي ذيل قصير يُدمج في المشهد السابق بدل أن يُرسم مشهدًا
    من ثلاث كلمات.
    """
    scenes: list[dict] = []
    buf: list[str] = []
    wc = 0

    def _flush() -> None:
        nonlocal buf, wc
        if buf:
            scenes.append({"narration": " ".join(buf).strip(), "words": wc})
            buf, wc = [], 0

    for paragraph in _PARAGRAPH_RE.split(text or ""):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        for s in arabic.split_sentences(paragraph):
            buf.append(s)
            wc += arabic.word_count(s)
            strong = s.endswith(("؟", "!", ":")) and wc >= MIN_SCENE_WORDS
            if wc >= SCENE_WORDS_TARGET or strong:
                _flush()
        # a paragraph is a hard boundary: never merge across it
        _flush()

    # merge a too-short tail into the scene before it
    if len(scenes) > 1 and scenes[-1]["words"] < MIN_MERGE_WORDS:
        tail = scenes.pop()
        scenes[-1]["narration"] = (
            scenes[-1]["narration"] + " " + tail["narration"]
        ).strip()
        scenes[-1]["words"] += tail["words"]
    return scenes


def infer_needs(text: str) -> list[str]:
    needs: list[str] = []
    t = arabic.normalize(text)
    for need, hints in NEED_HINTS.items():
        for h in hints:
            if arabic.normalize(h) in t:
                if need not in needs:
                    needs.append(need)
                break
    return needs or ["symbol"]


def heuristic_entities(text: str) -> list[dict]:
    """مستخرج احتياطي محسّن (قوائم دول/مناطق + أنماط أحداث/معاهدات/أشخاص/منظمات)."""
    ents: list[dict] = []
    seen: set[str] = set()

    def add(etype: str, name: str, needs: list[str], context: str = ""):
        name = name.strip(" ،,.")
        key = arabic.normalize(name)
        if key in seen or len(key) < 3:
            return
        seen.add(key)
        etype, needs = _apply_memory(name, etype, list(needs))
        ents.append({"type": etype, "name": name, "needs": needs, "context": context[:180]})

    # كلمات تكسر العبارة (حروف جر/عطف مستقلة)
    SPLIT_WORDS = ("و", "أو", "ثم", "في", "على", "من", "إلى", "بين", "حتى", "بعد", "قبل", "خلال", "ضد", "مع")
    # كلمات تبدأ بواو لكنها ليست عطفًا
    W_EXCEPTIONS = ("وادي", "واشنطن", "ولايات", "وهران", "وترلو", "ويمبلدون", "ووهان", "وارسو")

    def _split_groups(words: list[str]) -> list[list[str]]:
        groups: list[list[str]] = [[]]
        for w in words:
            if w in SPLIT_WORDS:
                break
            if w.startswith("و") and len(w) >= 4 and w not in W_EXCEPTIONS:
                groups.append([w[1:]])
            else:
                groups[-1].append(w)
        return [g for g in groups if g]

    def find_phrase(prefix: str, max_extra: int = 2) -> list[str]:
        """يعيد عبارات كاملة، ويفكّها عند العطف: «معركة السوم وفردان» → [«معركة السوم», «معركة فردان»]."""
        pat = re.compile(rf"(?<![\u0600-\u06FF]){re.escape(prefix)}\s+([\u0600-\u06FF]{{3,}}(?:\s+[\u0600-\u06FF]{{3,}}){{0,{max_extra}}})")
        out: list[str] = []
        for m in pat.finditer(text):
            groups = _split_groups(m.group(1).split())
            for g in groups:
                phrase = f"{prefix} {' '.join(g)}".strip()
                if len(phrase) > len(prefix) + 3:
                    out.append(phrase)
        return out

    # أحداث ومعاهدات
    for pref in EVENT_PREFIXES:
        etype = "event"
        needs = ["document"] if pref in DOCUMENT_PREFIXES else ["event", "map"]
        for full in find_phrase(pref):
            add(etype, full, list(needs))

    # دول
    for c in COUNTRY_LIST:
        if re.search(rf"(?<![\u0600-\u06FF]){re.escape(c)}(?![\u0600-\u06FF])", text):
            add("country", c, ["flag", "map"])

    # مناطق ومدن
    for r in REGION_LIST:
        if re.search(rf"(?<![\u0600-\u06FF]){re.escape(r)}(?![\u0600-\u06FF])", text):
            add("city", r, ["map"])

    # أشخاص (لقب + اسم)
    for title in PERSON_TITLES:
        for full in find_phrase(title, max_extra=1):
            add("person", full, ["portrait"])

    # منظمات/إمبراطوريات
    for pref in ORG_PREFIXES:
        for full in find_phrase(pref, max_extra=2):
            add("org", full, ["symbol", "document"])

    # أسماء لاتينية
    for m in CAPS_RE.finditer(text):
        name = m.group(1).strip()
        add("concept", name, infer_needs(name))

    # تواريخ
    for d in arabic.find_dates(text)[:12]:
        add("date", d, [])

    return ents[:28]


def heuristic_claims(text: str) -> list[dict]:
    """ادّعاءات أولية: كل جملة فيها رقم/تاريخ = ادّعاء يحتاج تحققًا."""
    claims: list[dict] = []
    for i, s in enumerate(arabic.split_sentences(text), 1):
        nums = arabic.find_numbers(s)
        dates = arabic.find_dates(s)
        if nums or dates:
            claims.append(
                {
                    "id": f"c{i}",
                    "text": s[:220],
                    "type": "تاريخي" if dates else "رقم",
                    "risk": "med",
                    "numbers": nums[:5],
                    "dates": dates[:3],
                }
            )
    return claims[:24]


def heuristic_script_graph(text: str) -> dict:
    scenes = heuristic_scenes(text)
    duration = estimate_duration(text)
    out_scenes = []
    for i, s in enumerate(scenes, 1):
        w = s["words"]
        out_scenes.append(
            {
                "id": i,
                "narration": s["narration"],
                "duration": round(w / WORDS_PER_SECOND, 2),
                "needs": infer_needs(s["narration"]),
                "keywords": [k for k, _ in arabic.keywords(s["narration"], top=6)],
            }
        )
    words = arabic.word_count(text)
    return {
        "engine": "heuristic",
        "lang": "ar" if arabic.is_arabic(text) else "en",
        "tone": "تعليمي",
        "audience": "عام",
        "hook": scenes[0]["narration"][:120] if scenes else "",
        "claims": heuristic_claims(text),
        "entities": heuristic_entities(text),
        "timeline": [{"when": d, "what": ""} for d in arabic.find_dates(text)[:20]],
        "quotes": arabic.find_quotes(text)[:10],
        "numbers": arabic.find_numbers(text)[:30],
        "scenes": out_scenes,
        "stats": {
            "words": words,
            "sentences": len(arabic.split_sentences(text)),
            "scenes": len(out_scenes),
            "estimated_duration": round(duration, 1),
        },
        "source_hash": sha256_text(text)[:16],
    }


# ---------- استدعاء LLM مشهد-بمشهد (أدق للموديلات الصغيرة) ----------

SCENE_SYSTEM_PROMPT = """\
أنت محلّل بصري لسكريبتات فيديو الوايت بورد. تُعطى جملة عربية واحدة.
مهمتك: استخراج الكيانات القابلة للرسم + الادّعاءات.
قواعد صارمة:
1) اسم كل كيان يجب أن يظهر حرفيًا داخل الجملة (لا تخترع، لا تترجم).
2) type من: person | country | city | event | org | concept | date | object
3) needs من: portrait | event | map | flag | chart | document | object | symbol
4) لا تنسخ نص المخطط، لا شرح، JSON فقط.
"""

SCENE_USER_TEMPLATE = """\
الجملة ({idx}): «{text}»

أعد JSON فقط:
{{"scene": {idx}, "entities": [{{"name": "اسم حرفي من الجملة", "type": "person", "needs": ["portrait"], "why": "كلمات دالة من الجملة"}}], "claims": [{{"text": "مقتطف حرفي قصير", "type": "تاريخي", "risk": "med"}}], "visual": "وصف بصري مختصر لما يُرسم"}}
"""

ECHO_MARKERS = ("كما في النص", "الاسم كما", "وصف النبرة", "your answer", "example", "مثال", "...")


def _appears(phrase: str, haystack_norm: str) -> bool:
    """هل العبارة فعلًا موجودة في النص (مع تسامح في أل التعريف/التشكيل)؟"""
    p = arabic.normalize(phrase)
    if len(p) < 3:
        return False
    if p in haystack_norm:
        return True
    words = [w for w in p.split() if len(w) > 2]
    if not words:
        return False
    hits = sum(1 for w in words if w in haystack_norm)
    return hits >= max(1, int(len(words) * 0.7))


def _clean_entities(items: list, scene_text: str, scene_text_norm: str) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for e in items or []:
        if not isinstance(e, dict):
            continue
        name = str(e.get("name", "")).strip()
        if not name or len(name) < 3:
            continue
        if any(mk in name for mk in ECHO_MARKERS):
            continue
        if not _appears(name, scene_text_norm):
            continue
        key = arabic.normalize(name)
        if key in seen:
            continue
        seen.add(key)
        etype = str(e.get("type", "concept")).strip()
        if etype not in ("person", "country", "city", "event", "org", "concept", "date", "object"):
            etype = "concept"
        needs = [n for n in (e.get("needs") or []) if isinstance(n, str) and n in NEED_HINTS]
        out.append({"name": name, "type": etype, "needs": needs[:5] or infer_needs(name), "why": str(e.get("why", ""))[:120]})
    return out


def analyze_script(text: str, *, llm: LLM | None = None, force_offline: bool = False, max_scenes_llm: int = 40) -> dict:
    """السكريبت → ScriptGraph.

    الاستراتيجية: التقسيم والاحتياط محلي دائمًا، ثم الـLLM يُثري (مشهد-بمشهد) مع تحقق صارم؛
    أي فشل أو تخريف → نعود للمحلي بدون كسر.
    """
    text = text.strip()
    if not text:
        raise ValueError("سكريبت فارغ")
    base = heuristic_script_graph(text)
    client = llm or LLM()
    if force_offline or not client.available:
        return base

    text_norm = arabic.normalize(text)
    annotations: dict[int, dict] = {}
    ok = 0
    for s in base["scenes"][:max_scenes_llm]:
        try:
            data = client.ask_json(SCENE_SYSTEM_PROMPT, SCENE_USER_TEMPLATE.format(idx=s["id"], text=s["narration"]), temperature=0.1)
        except LLMError:
            data = None
        if isinstance(data, dict):
            ok += 1
            annotations[s["id"]] = data

    if ok == 0:
        base["engine"] = f"llm:{client.backend()}:failed→heuristic"
        return base

    merged = _merge_annotations(base, annotations, text_norm)
    merged["engine"] = f"llm-scenes:{client.backend()}"
    merged["stats"]["llm_scenes_ok"] = ok
    return merged


def _merge_annotations(base: dict, annotations: dict[int, dict], text_norm: str) -> dict:
    """يدمج إثراءات المشاهد في الرسم الأساسي مع التحقق والتنقية."""
    entities: list[dict] = []
    claims: list[dict] = list(base.get("claims", []))
    n_claim = len(claims)

    def push_entity(e: dict, scene_id: int):
        e = dict(e)
        e["type"], e["needs"] = _apply_memory(e.get("name", ""), e.get("type", "concept"), list(e.get("needs") or []))
        key = arabic.normalize(e["name"])
        for i, existing in enumerate(entities):
            ek = arabic.normalize(existing["name"])
            if ek == key or ek in key or key in ek:
                # دمج: احتفظ بالأطول اسمًا واجمع الاحتياجات
                if len(key) > len(ek):
                    existing["name"] = e["name"]
                existing["needs"] = list(dict.fromkeys(existing.get("needs", []) + e.get("needs", [])))[:6]
                if e.get("type") not in ("concept",) and existing.get("type") == "concept":
                    existing["type"] = e["type"]
                existing.setdefault("scenes", []).append(scene_id)
                return
        e2 = dict(e)
        e2["scenes"] = [scene_id]
        entities.append(e2)

    for s in base["scenes"]:
        ann = annotations.get(s["id"], {})
        s_norm = arabic.normalize(s["narration"])
        for e in _clean_entities(ann.get("entities", []), s["narration"], s_norm):
            push_entity(e, s["id"])
        for c in ann.get("claims", []) or []:
            if not isinstance(c, dict):
                continue
            ctext = str(c.get("text", "")).strip()
            if len(ctext) < 6 or not _appears(ctext[:80], s_norm):
                continue
            n_claim += 1
            claims.append({"id": f"c{n_claim}", "text": ctext[:220], "type": str(c.get("type", "عام"))[:24], "risk": str(c.get("risk", "med"))[:8], "scene": s["id"]})
        visual = str(ann.get("visual", "")).strip()
        if visual and len(visual) > 4:
            s["visual"] = visual[:200]
        llm_needs = [n for n in (ann.get("needs") or []) if isinstance(n, str)]
        if llm_needs:
            s["needs"] = list(dict.fromkeys(s.get("needs", []) + llm_needs))[:5]

    # لو الـLLM ما لقاش كيانات، نرجع لكيانات الاحتياط مع احتياجاتها
    if not entities:
        entities = [dict(e) for e in base.get("entities", [])]

    out = dict(base)
    out["entities"] = entities[:28]
    out["claims"] = claims[:60]
    out["stats"] = dict(base.get("stats", {}))
    out["stats"]["claims"] = len(out["claims"])
    out["stats"]["entities"] = len(out["entities"])
    return out


SYSTEM_PROMPT = """\
أنت محلّل سكريبت محترف لمحرك فيديو وثائقي (وايت بورد). مهمتك: تفكيك النص إلى بنية إنتاج دقيقة.
قواعد صارمة:
1) لا تخترع معلومات غير موجودة في النص. الكيانات تُستخرج من النص.
2) كل ادّعاء رقمي/تاريخي/اقتباس = claim مستقل.
3) كل كيان يُصنّف: person | country | city | event | org | concept | date | object.
4) حدد لكل كيان "needs" بصرية من: portrait, event, map, flag, chart, document, object, symbol.
5) قسّم لمشاهد: كل مشهد 12-22 كلمة، بالترتيب الأصلي.
6) أعد JSON فقط وفق المخطط.
"""

# قوائم مساعدة للتحليل الاحتياطي
COUNTRY_LIST = (
    "ألمانيا", "فرنسا", "بريطانيا", "روسيا", "الولايات المتحدة", "المملكة المتحدة", "إيطاليا", "اليابان",
    "الصين", "الهند", "مصر", "السعودية", "العراق", "سوريا", "لبنان", "فلسطين", "الأردن", "المغرب",
    "الجزائر", "تونس", "ليبيا", "السودان", "اليمن", "عُمان", "قطر", "الكويت", "البحرين", "الإمارات",
    "تركيا", "إيران", "اليونان", "إسبانيا", "البرتغال", "هولندا", "بلجيكا", "السويد", "النرويج",
    "الدنمارك", "فنلندا", "بولندا", "أوكرانيا", "النمسا", "المجر", "رومانيا", "بلغاريا", "صربيا",
    "كرواتيا", "ألبانيا", "سويسرا", "كندا", "أستراليا", "البرازيل", "الأرجنتين", "المكسيك", "تشيلي",
    "كوريا", "فيتنام", "إندونيسيا", "باكستان", "أفغانستان", "نيجيريا", "كينيا", "إثيوبيا", "جنوب أفريقيا",
)
REGION_LIST = (
    "أوروبا", "آسيا", "أفريقيا", "أمريكا الشمالية", "أمريكا الجنوبية", "الشرق الأوسط", "الشرق الأقصى",
    "البلقان", "الشام", "الخليج", "شبه الجزيرة العربية", "شمال أفريقيا", "البحر المتوسط", "المحيط الأطلسي",
    "المحيط الهادئ", "البحر الأحمر", "القسطنطينية", "الأناضول", "الصحراء الكبرى",
)
EVENT_PREFIXES = (
    "حرب", "معركة", "ثورة", "غزو", "احتلال", "انقلاب", "مذبحة", "حصار", "هجوم", "مؤتمر", "اتفاق",
    "معاهدة", "إعلان", "استقلال", "سقوط", "انهيار", "زلزال", "اكتشاف", "هجرة", "مظاهرة", "انتخابات",
    "مؤامرة", "فتح", "تحرير",
)
DOCUMENT_PREFIXES = ("معاهدة", "اتفاق", "وثيقة", "دستور", "قانون", "خطاب", "رسالة", "تقرير", "مخطوطة")
PERSON_TITLES = (
    "الأرشيدوق", "الملك", "الملكة", "الرئيس", "الزعيم", "القائد", "الإمبراطور", "السلطان", "الخليفة",
    "الأمير", "الأميرة", "الجنرال", "الدكتور", "المهندس", "العالم", "الكاتب", "الفيلسوف", "البابا",
    "المستشار", "الوزير", "الخديوي", "المارشال", "الملقب", "الشيخ", "العلامة", "المفكر", "المؤرخ",
)
ORG_PREFIXES = ("الإمبراطورية", "الدولة", "المملكة", "الجمهورية", "الاتحاد", "الحلف", "العصبة", "المنظمة",
                "الحكومة", "البرلمان", "الجيش", "الأسطول", "الأمم")


USER_TEMPLATE = """\
النص:
\"\"\"{script}\"\"\"

أعد JSON بالمخطط التالي حرفيًا (بدون شرح):
{{
 "lang": "ar|en",
 "tone": "وصف النبرة",
 "audience": "الجمهور المستهدف",
 "hook": "أول جملة جذب حرفية",
 "claims": [{{"id":"c1","text":"...","type":"تاريخي|رقم|اقتباس|علمي","risk":"low|med|high"}}],
 "entities": [{{"id":"e1","type":"person|country|city|event|org|concept|date|object","name":"الاسم كما في النص","needs":["portrait"],"context":"وصف مختصر من النص"}}],
 "timeline": [{{"when":"التاريخ كما ورد","what":"الحدث","entity":"e1"}}],
 "beats": [{{"idea":"الفكرة","emotion":"المشاعر","visual":["map","photo"]}}],
 "scenes": [{{"id":1,"narration":"نص المشهد الحرفي","duration":8.5,"needs":["map"],"keywords":["..."]}}],
 "stats": {{"words":0,"scenes":0,"estimated_duration":0}}
}}
"""


def analyze_whole_graph(text: str, *, llm: LLM | None = None) -> dict | None:
    """مسار الموديلات الكبيرة: تحليل السكريبت كاملًا دفعة واحدة (يُستخدم اختياريًا)."""
    client = llm or LLM()
    if not client.available:
        return None
    try:
        data = client.ask_json(SYSTEM_PROMPT, USER_TEMPLATE.format(script=text))
    except LLMError as e:
        from ..core.log import get_logger

        get_logger("understanding").warning("فشل LLM الكامل: %s", e)
        return None
    graph = _normalize_graph(data, text)
    graph["engine"] = f"llm-whole:{client.backend()}"
    return graph


def _normalize_graph(data: dict, text: str) -> dict:
    """يضمن اكتمال الحقول وترابط المعرّفات."""
    graph = {
        "lang": data.get("lang") or ("ar" if arabic.is_arabic(text) else "en"),
        "tone": data.get("tone", ""),
        "audience": data.get("audience", ""),
        "hook": data.get("hook", ""),
        "claims": [],
        "entities": [],
        "timeline": [],
        "beats": data.get("beats", []) or [],
        "quotes": arabic.find_quotes(text)[:10],
        "numbers": arabic.find_numbers(text)[:30],
        "scenes": [],
        "stats": {},
        "source_hash": sha256_text(text)[:16],
    }
    for i, c in enumerate(data.get("claims", []) or [], 1):
        graph["claims"].append(
            {
                "id": c.get("id") or f"c{i}",
                "text": str(c.get("text", "")).strip(),
                "type": c.get("type", ""),
                "risk": c.get("risk", "med"),
            }
        )
    for i, e in enumerate(data.get("entities", []) or [], 1):
        name = str(e.get("name", "")).strip()
        if not name:
            continue
        needs = [n for n in (e.get("needs") or []) if isinstance(n, str)] or infer_needs(name)
        etype, needs = _apply_memory(name, str(e.get("type", "concept")), needs)
        graph["entities"].append(
            {
                "id": e.get("id") or f"e{i}",
                "type": etype,
                "name": name,
                "needs": needs[:6],
                "context": e.get("context", ""),
            }
        )
    for t in data.get("timeline", []) or []:
        graph["timeline"].append({"when": str(t.get("when", "")), "what": str(t.get("what", "")), "entity": t.get("entity")})
    for i, s in enumerate(data.get("scenes", []) or [], 1):
        narration = str(s.get("narration", "")).strip()
        if not narration:
            continue
        dur = s.get("duration")
        try:
            dur = float(dur)
        except Exception:
            dur = round(arabic.word_count(narration) / WORDS_PER_SECOND, 2)
        graph["scenes"].append(
            {
                "id": s.get("id") or i,
                "narration": narration,
                "duration": max(2.0, dur),
                "needs": [n for n in (s.get("needs") or []) if isinstance(n, str)] or infer_needs(narration),
                "keywords": [k for k in (s.get("keywords") or []) if isinstance(k, str)][:8],
            }
        )
    if not graph["scenes"]:
        graph["scenes"] = heuristic_script_graph(text)["scenes"]
    total = sum(s["duration"] for s in graph["scenes"])
    graph["stats"] = {
        "words": arabic.word_count(text),
        "sentences": len(arabic.split_sentences(text)),
        "scenes": len(graph["scenes"]),
        "estimated_duration": round(total, 1),
        "claims": len(graph["claims"]),
        "entities": len(graph["entities"]),
    }
    return graph


def save_graph(graph: dict, project_dir, filename: str = "scriptgraph.json"):
    return write_json(project_dir / "script" / filename, graph)
