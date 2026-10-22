"""بوابة الملاءمة الدلالية للأصول — تقتل «البحث بالاسم».

المشكلة المقيسة
----------------
البحث يجد الملف **باسم الكيان** لا بمضمونه: «Qi Jiguang» تُرجع مخططات
سفن حديثة، و«Sun Zi» تُرجع صفحة من ترجمة فرنسية، و«Japan» تُرجع خريطة
 bathymetric. في حلقة «فن الحرب» رُفض **8 من 26** أصلًا بالعين البشرية
لهذا السبب بالذات. المحرك كان يشرح الرفض ولا يمنعه.

هذه الوحدة تحوّل العنوان+الوصف إلى **حكم ملاءمة** قبل التنزيل:

* ``heuristic``: إشارات نصية قابلة للقياس (تداخل الرموز، نوع الأصل، زمن
  العنصر مقابل زمن الكيان) — تعمل دائمًا بلا موديل.
* ``llm``: حكم دلالي بالموديل المحلي على «هل يصف العنوان ما يحتاجه
  المشهد؟» — يعالج حالة «الاسم صحيح والمضمون خطأ».
* الدمج **متحفّظ**: لا يُعتمد أصل إلا بموافقة صريحة؛不确定性 تعني
  «يحتاج عينًا بشرية» لا «مقبول».

النتيجة تُكتب في ``research/relevance.json`` كسجل قابل للمراجعة.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Sequence

from ..core.log import get_logger

log = get_logger("research.relevance")

VERDICTS = ("relevant", "uncertain", "irrelevant")
REPORT_NAME = "relevance.json"

# كلمات وظيفية لا تُحتسب في التداخل
STOP = {
    "the", "a", "an", "of", "in", "on", "at", "to", "for", "and", "or", "by",
    "from", "with", "is", "are", "was", "were", "this", "that", "its", "his",
    "her", "their", "file", "image", "picture", "photo", "commons", "wikipedia",
    "من", "في", "على", "إلى", "عن", "مع", "هذا", "التي", "الذي", "كان", "صور",
    "صورة", "ملف",
}

# كلمات تدلّ على أن الأصل ليس من نوع ما يحتاجه المشهد
_PORTRAIT_BLOCKERS = {
    "map", "maps", "flag", "flags", "book", "books", "page", "pages", "plan",
    "plans", "chart", "logo", "coat", "arms", "diagram", "seal", "coin",
    "stamp", "poster", "banner", "statue", "monument", "grave", "tomb",
    "train", "locomotive", "railway", "station", "ship", "boat", "bridge",
    "aircraft", "plane", "car", "motorcycle", "wrench", "gun", "rifle",
    "cannon", "warship", "bathymetric", "relief", "photo", "photograph",
    "painting", "portrait",
}
_MAP_BLOCKERS = {
    "portrait", "portraits", "flag", "flags", "book", "manuscript", "letter",
    "signature", "wrench", "train", "locomotive", "warship", "photo",
    "photograph", "shell", "shells", "bronze", "painting",
}
_DOCUMENT_BLOCKERS = {
    "portrait", "flag", "train", "locomotive", "warship", "map", "relief",
    "bathymetric", "photo", "photograph", "statue",
}

_KIND_BLOCKERS = {
    "portrait": _PORTRAIT_BLOCKERS,
    "map": _MAP_BLOCKERS,
    "document": _DOCUMENT_BLOCKERS,
    "event": set(),
}


@dataclass
class Verdict:
    """حكم ملاءمة أصل واحد."""

    id: str
    verdict: str = "uncertain"
    score: float = 0.0
    reason: str = ""
    judge: str = "heuristic"
    signals: list[str] = field(default_factory=list)

    @property
    def allowed(self) -> bool:
        """هل يُسمح للأصل بدخول المشروع تلقائيًّا؟"""
        return self.verdict == "relevant"

    def to_dict(self) -> dict:
        return asdict(self)


def _tokens(text: str) -> list[str]:
    words = re.split(r"[^\w؀-ۿ]+", str(text or "").lower())
    return [w for w in words if w and w not in STOP and len(w) > 1]


def _overlap(a: Sequence[str], b: Sequence[str]) -> float:
    if not a or not b:
        return 0.0
    sa, sb = set(a), set(b)
    return len(sa & sb) / float(len(sa | sb))


def heuristic_verdict(
    candidate: dict,
    context: dict,
    *,
    era_year: int | None = None,
) -> Verdict:
    """حكم نصي قابل للقياس — بلا موديل، ويعمل على أي جهاز.

    ``context``: ``{"name": ..., "type": ..., "need": ..., "why": ...}``
    """
    cid = str(candidate.get("id") or candidate.get("title") or "")
    title = str(candidate.get("title") or "")
    desc = str(candidate.get("description") or candidate.get("summary") or "")
    name = str(context.get("name") or "")
    need = str(context.get("need") or context.get("kind") or "")
    why = str(context.get("why") or "")
    scene = str(context.get("scene") or "")

    signals: list[str] = []
    title_tokens = _tokens(title)
    desc_tokens = _tokens(desc)
    req_tokens = _tokens(" ".join([name, why, scene]))

    score = _overlap(title_tokens, req_tokens)
    if desc_tokens:
        score = max(score, 0.75 * _overlap(desc_tokens, req_tokens))
    if name and name.lower() in title.lower():
        score += 0.15
        signals.append("name-in-title")
    if why and _overlap(_tokens(why), title_tokens) > 0.25:
        score += 0.1
        signals.append("why-overlap")

    # --- نوع الأصل: عنوان من نوع آخر = رفض قوي ---
    blockers = _KIND_BLOCKERS.get(need, set())
    if blockers:
        hit = sorted(blockers & set(title_tokens))
        if hit:
            score -= 0.45
            signals.append("wrong-kind:" + ",".join(hit[:3]))

    # --- زمن العنصر مقابل زمن الكيان ---
    years = [int(y) for y in re.findall(r"\b(1[89]\d{2}|20\d{2})\b", title)]
    if era_year and years:
        newest = max(years)
        if newest > era_year + 60:
            score -= 0.35
            signals.append(f"modern-for-era:{newest}>{era_year}")

    # --- نوع الملف: GIF/صغير الدقة ليس بديلًا عن المصدر ---
    if str(candidate.get("mime") or "").endswith("gif"):
        score -= 0.2
        signals.append("gif-format")

    score = max(0.0, min(1.0, score))
    negative = [s for s in signals if s.startswith(("wrong-kind", "modern-for-era", "gif-format"))]
    if negative:
        # دليل سلبي صريح (نوع خاطئ أو زمن متأخر) ⇒ رفض قبل التنزيل
        verdict = "irrelevant"
    elif score >= 0.45:
        verdict = "relevant"
    else:
        # لا دليل ينفي ولا يُثبت ⇒ «يحتاج عينًا بشرية»، لا رفضٌ بلا سند
        verdict = "uncertain"
    return Verdict(
        id=cid,
        verdict=verdict,
        score=round(score, 3),
        reason="heuristic: " + (", ".join(signals) if signals else "no evidence"),
        judge="heuristic",
        signals=signals,
    )


def _llm_prompt(candidates: list[dict], context: dict) -> tuple[str, str]:
    """يبني العقد: النظام + قائمة المرشّحين."""
    system = (
        "You are a strict visual-asset relevance reviewer for a documentary video. "
        "You judge whether a candidate asset's TITLE (and description) plausibly "
        "depicts what the scene needs. Answer with JSON only."
    )
    lines = []
    lines.append(f"Scene subject (entity): {context.get('name') or ''}")
    lines.append(f"Entity type: {context.get('type') or ''}")
    lines.append(f"Asset kind needed: {context.get('need') or ''}")
    if context.get("why"):
        lines.append(f"What the scene needs: {context['why']}")
    if context.get("scene"):
        lines.append(f"Narration of the scene: {context['scene']}")
    lines.append("")
    lines.append("Candidates:")
    for cand in candidates:
        desc = str(cand.get("description") or "").replace("\n", " ")[:220]
        lines.append(
            f"- id={cand.get('id')} | title={cand.get('title')} | "
            f"type={cand.get('type') or cand.get('kind') or ''} | desc={desc}"
        )
    lines.append("")
    lines.append(
        "For each id answer one of: relevant / uncertain / irrelevant.\n"
        "'relevant' = the title clearly indicates the asset shows the required subject.\n"
        "'irrelevant' = the title indicates a different subject (a modern warship for an "
        "ancient commander, a map for a portrait, a book page for a person, a train photo "
        "for a country, a relief map for a printed book).\n"
        "'uncertain' = the title is too vague to decide.\n"
        'Answer ONLY with JSON: {"items":[{"id":"...","verdict":"...","score":0.0,'
        '"reason":"<max 12 words"}]}'
    )
    return system, "\n".join(lines)


def llm_verdicts(
    candidates: list[dict],
    context: dict,
    *,
    llm=None,
    batch_size: int = 6,
) -> tuple[dict[str, Verdict], str]:
    """حكم دلالي بالموديل المحلي. يعيد (الأحكام، سبب الفشل)."""
    from ..providers.llm import LLM, LLMError

    client = llm or LLM()
    if not client.available:
        return {}, "llm-unavailable"
    system, user = _llm_prompt(candidates, context)
    out: dict[str, Verdict] = {}
    failure = ""
    for start in range(0, len(candidates), batch_size):
        chunk = candidates[start : start + batch_size]
        try:
            data = client.ask_json(system, user, temperature=0.0, retries=1)
        except LLMError as exc:
            failure = str(exc)
            break
        items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(items, list):
            failure = "llm-no-items"
            break
        for item in items:
            if not isinstance(item, dict):
                continue
            cid = str(item.get("id") or "")
            raw = str(item.get("verdict") or "").strip().lower()
            verdict = raw if raw in VERDICTS else "uncertain"
            try:
                score = float(item.get("score"))
            except (TypeError, ValueError):
                score = 0.5
            out[cid] = Verdict(
                id=cid,
                verdict=verdict,
                score=max(0.0, min(1.0, score)),
                reason=str(item.get("reason") or "")[:200],
                judge="llm",
            )
    return out, failure


def fuse(heur: Verdict, llm: Verdict | None) -> Verdict:
    """دمج الحكمين بقاعدة متحفّظة.

    * حكم LLM «غير ذي صلة» حاسم (يُسقط الأصل قبل التنزيل).
    * حكم LLM «ذي صلة» **لا يُعتمد** وحده: لازم إشارة نصية توافق ⇒ وإلّا
      يبقى «يحتاج عينًا بشرية».
    """
    if llm is None:
        return heur
    signals = list(heur.signals)
    if llm.verdict == "irrelevant":
        return Verdict(
            id=heur.id,
            verdict="irrelevant",
            score=min(heur.score, llm.score),
            reason=f"llm: {llm.reason}" if llm.reason else "llm: irrelevant",
            judge="llm+heuristic",
            signals=signals + ["llm-irrelevant"],
        )
    if llm.verdict == "uncertain":
        return Verdict(
            id=heur.id,
            verdict="uncertain",
            score=min(heur.score, llm.score),
            reason=f"llm: {llm.reason}" if llm.reason else "llm: uncertain",
            judge="llm+heuristic",
            signals=signals + ["llm-uncertain"],
        )
    # llm says relevant
    if heur.verdict == "relevant":
        return Verdict(
            id=heur.id,
            verdict="relevant",
            score=max(heur.score, llm.score),
            reason=f"llm: {llm.reason}" if llm.reason else "llm+heuristic agree",
            judge="llm+heuristic",
            signals=signals + ["llm-relevant"],
        )
    return Verdict(
        id=heur.id,
        verdict="uncertain",
        score=llm.score,
        reason="llm says relevant, the text signals do not agree — needs a human look",
        judge="llm+heuristic",
        signals=signals + ["conflict-needs-human"],
    )


def judge_candidates(
    candidates: list[dict],
    context: dict,
    *,
    era_year: int | None = None,
    use_llm: bool = True,
    llm=None,
) -> list[Verdict]:
    """يحكم كل المرشّحين ويعيد قائمة أحكام (ترتيب المرشّحين محفوظ)."""
    prepared: list[dict] = []
    for index, cand in enumerate(candidates):
        item = dict(cand)
        item.setdefault("id", f"c{index + 1}")
        prepared.append(item)

    heur = {
        item["id"]: heuristic_verdict(item, context, era_year=era_year) for item in prepared
    }
    llm_map: dict[str, Verdict] = {}
    failure = ""
    if use_llm:
        llm_map, failure = llm_verdicts(prepared, context, llm=llm)
        if failure:
            log.warning("الحكم الدلالي لم يكتمل (%s) — يبقى الحكم النصي وحده", failure)
    verdicts = [fuse(heur[item["id"]], llm_map.get(item["id"])) for item in prepared]
    for verdict in verdicts:
        if verdict.judge == "heuristic" and failure:
            verdict.reason = f"{verdict.reason} ({failure})"
    return verdicts


# --------------------------------------------------------------------------
# بوابة قابلة لإعادة الاستخدام (مع ذاكرة مؤقتة)
# --------------------------------------------------------------------------
class RelevanceGate:
    """بوابة ملاءمة تُستدعى من البحث والخطة.

    * ذاكرة مؤقتة بالمفتاح (الأصل + الكيان + الاحتياج) — لا حكم مزدوج.
    * الحكم الدلالي يُستدعى **فقط** حين لا يحسم النصُّ الأمر (الحالة
      «الاسم صحيح والمضمون خطأ»).
    * بلا موديل: الحكم النصي وحده — والبلاوغ «يحتاج عينًا» لا «مرفوض».
    """

    def __init__(self, *, use_llm: bool = True, llm=None, llm_min_score: float = 0.5):
        self.use_llm = bool(use_llm)
        self._llm = llm
        self.llm_min_score = float(llm_min_score)
        self._cache: dict[tuple, Verdict] = {}
        self.calls = 0
        self.llm_calls = 0
        self.failures: list[str] = []

    @staticmethod
    def key(candidate: dict, context: dict) -> tuple:
        return (
            str(candidate.get("id") or candidate.get("path") or candidate.get("title") or ""),
            str(context.get("name") or ""),
            str(context.get("need") or ""),
        )

    def judge(self, candidate: dict, context: dict, *, era_year: int | None = None) -> Verdict:
        k = self.key(candidate, context)
        cached = self._cache.get(k)
        if cached is not None:
            return cached
        self.calls += 1
        heur = heuristic_verdict(candidate, context, era_year=era_year)
        verdict = heur
        if self.use_llm and heur.verdict == "uncertain":
            llm = self._llm
            try:
                from ..providers.llm import LLM

                llm = llm or LLM()
            except Exception:
                llm = None
            if llm is not None and getattr(llm, "available", False):
                self.llm_calls += 1
                try:
                    prepared = [dict(candidate)]
                    prepared[0].setdefault("id", k[0] or "c1")
                    llm_map, failure = llm_verdicts(prepared, context, llm=llm)
                    if failure:
                        self.failures.append(failure)
                    verdict = fuse(heur, llm_map.get(k[0]))
                except Exception as exc:  # عطل الموديل لا يُسقط البحث
                    self.failures.append(str(exc))
        self._cache[k] = verdict
        return verdict


# --------------------------------------------------------------------------
# تقرير قابل للمراجعة
# --------------------------------------------------------------------------
def build_report(
    groups: list[dict],
    *,
    source: str = "",
    note: str = "",
) -> dict:
    """يبني تقرير الملاءمة: لكل مجموعة أحكامها، وفيه ملخّص."""
    items: list[dict] = []
    counts = {"relevant": 0, "uncertain": 0, "irrelevant": 0}
    for group in groups:
        for verdict in group.get("verdicts") or []:
            counts[verdict.verdict] = counts.get(verdict.verdict, 0) + 1
            items.append(
                {
                    **verdict.to_dict(),
                    "entity": group.get("name"),
                    "need": group.get("need"),
                    "title": group.get("titles", {}).get(verdict.id, ""),
                }
            )
    return {
        "generated_at": None,
        "source": source,
        "note": note,
        "counts": counts,
        "items": items,
    }


def write_report(report: dict, project_dir) -> Any:
    from ..core.util import write_json
    from datetime import datetime, timezone

    report["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    path = write_json(f"{project_dir}/research/{REPORT_NAME}", report)
    return path


def load_report(project_dir) -> dict | None:
    from ..core.util import read_json

    return read_json(f"{project_dir}/research/{REPORT_NAME}", default=None)


__all__ = [
    "REPORT_NAME",
    "VERDICTS",
    "RelevanceGate",
    "Verdict",
    "build_report",
    "fuse",
    "heuristic_verdict",
    "judge_candidates",
    "llm_verdicts",
    "load_report",
    "write_report",
]
