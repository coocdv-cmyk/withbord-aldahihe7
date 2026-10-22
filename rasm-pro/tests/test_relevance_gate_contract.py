"""العقد: بوابة الملاءمة — تحكم قبل التنزيل، ولا تدّعي ما لا تعرف.

القواعد المقيسة على بيانات مُعنونة بحكم بشري (حلقة «فن الحرب»: 8 مرفوضات
و18 معتمدات):

* الحكم النصي (بلا موديل) يمسك الحالات الصريحة: نوع خاطئ، زمن متأخر، GIF.
* لا دليل ⇒ «يحتاج عينًا» **لا** «مرفوض» (رفض بلا سند = كسر).
* الحكم الدلالي بالموديل المحلي يقتل حالة «الاسم صحيح والمضمون خطأ».
* الدمج متحفّظ: لا يُعتمد أصل إلا بموافقة صريحة.
"""
from __future__ import annotations

from engine.research.relevance import (
    RelevanceGate,
    Verdict,
    fuse,
    heuristic_verdict,
    judge_candidates,
)


def _cand(cid: str, title: str, **extra) -> dict:
    item = {"id": cid, "title": title}
    item.update(extra)
    return item


def test_a_wrong_kind_is_rejected_without_a_model():
    verdict = heuristic_verdict(
        _cand("c1", "File:Diesel locomotive ChME3 in Vinnitsa railway station, Ukraine.jpg"),
        {"name": "Ukraine", "need": "map", "type": "country"},
    )
    assert verdict.verdict == "irrelevant"
    assert any(s.startswith("wrong-kind") for s in verdict.signals)


def test_a_modern_asset_for_an_ancient_subject_is_flagged():
    verdict = heuristic_verdict(
        _cand("c1", "File:PLANS Qi Jiguang 83 (ship, 2017) 20190621.jpg"),
        {"name": "Qi Jiguang", "need": "portrait", "type": "person"},
        era_year=1528,
    )
    assert verdict.verdict == "irrelevant"
    assert any(s.startswith("modern-for-era") for s in verdict.signals)


def test_no_evidence_means_needs_a_human_never_a_rejection():
    verdict = heuristic_verdict(
        _cand("c1", "File:Sunzi, Author of Art of War (9873714545).jpg"),
        {"name": "Sun Tzu", "need": "portrait", "type": "person"},
    )
    assert verdict.verdict == "uncertain"
    assert verdict.verdict != "irrelevant"


def test_the_llm_verdict_is_never_ignored():
    heur = Verdict(id="c1", verdict="uncertain", score=0.3, reason="no evidence")
    llm = Verdict(id="c1", verdict="irrelevant", score=0.9, reason="a train photo")
    out = fuse(heur, llm)
    assert out.verdict == "irrelevant"
    assert "train" in out.reason


def test_a_conflict_goes_to_the_human_not_to_auto_approval():
    heur = Verdict(id="c1", verdict="irrelevant", score=0.1, reason="wrong-kind")
    llm = Verdict(id="c1", verdict="relevant", score=0.8, reason="looks right")
    out = fuse(heur, llm)
    assert out.verdict == "uncertain"
    assert "human" in out.reason.lower() or "needs" in out.reason.lower()


def test_the_gate_caches_its_judgements():
    gate = RelevanceGate(use_llm=False)
    cand = _cand("c1", "File:Map of Ukraine.svg")
    context = {"name": "Ukraine", "need": "map", "type": "country"}
    first = gate.judge(cand, context)
    second = gate.judge(cand, context)
    assert first is second
    assert gate.calls == 1


def test_the_judge_preserves_the_candidate_order():
    candidates = [
        _cand("c1", "File:A train in Ukraine.jpg"),
        _cand("c2", "File:Map of Ukraine.svg"),
        _cand("c3", "File:Unknown thing.jpg"),
    ]
    verdicts = judge_candidates(
        candidates,
        {"name": "Ukraine", "need": "map", "type": "country"},
        use_llm=False,
    )
    assert [v.id for v in verdicts] == ["c1", "c2", "c3"]
    assert verdicts[0].verdict == "irrelevant"
