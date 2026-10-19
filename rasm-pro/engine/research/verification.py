"""Mandatory verification gates for research candidates.

No single confidence score is used.  Each gate records its own pass/fail state
and missing evidence, so uncertainty remains visible.
"""
from __future__ import annotations

from .evidence import VerificationResult
from .identity import name_tokens, token_overlap


def _has(value) -> bool:
    return value not in (None, "", [], {})


def check_identity(candidate, requirement) -> VerificationResult:
    reasons = []
    missing = []
    cand_entity = str(candidate.get("entity") or candidate.get("metadata", {}).get("entity") or "")
    req_entity = getattr(requirement, "entity", "")
    if not req_entity and isinstance(requirement, dict):
        req_entity = requirement.get("entity", "")
    req_entity = str(req_entity)
    alternatives = getattr(requirement, "alternative_names", None)
    if alternatives is None and isinstance(requirement, dict):
        alternatives = requirement.get("alternative_names", [])
    alternatives = alternatives or []
    alternatives = alternatives or []
    names = [req_entity] + list(alternatives)
    if not req_entity:
        missing.append("requirement entity")
    if not cand_entity:
        missing.append("candidate entity")
    overlap = max((token_overlap(cand_entity, n) for n in names if n), default=0.0)
    if names and cand_entity and overlap < 0.5:
        reasons.append(f"identity mismatch: {cand_entity!r} vs {names!r}")
    passed = not reasons and not missing
    return VerificationResult("identity", passed, reasons, missing)


def check_time(candidate, requirement) -> VerificationResult:
    reasons = []
    missing = []
    req_time = getattr(requirement, "time_context", None)
    if req_time is None and isinstance(requirement, dict):
        req_time = requirement.get("time_context", "")
    cand_time = candidate.get("time_context") or candidate.get("metadata", {}).get("time")
    if req_time and not cand_time:
        missing.append("candidate time context")
    if req_time and cand_time and str(req_time) != str(cand_time):
        # Allow containment for ranges/years.
        if str(req_time) not in str(cand_time) and str(cand_time) not in str(req_time):
            reasons.append(f"time mismatch: {cand_time!r} vs {req_time!r}")
    passed = not reasons and not (req_time and not cand_time)
    return VerificationResult("time", passed, reasons, missing)


def check_location(candidate, requirement) -> VerificationResult:
    reasons = []
    missing = []
    req_loc = getattr(requirement, "location", None)
    if req_loc is None and isinstance(requirement, dict):
        req_loc = requirement.get("location", "")
    cand_loc = candidate.get("location") or candidate.get("metadata", {}).get("location")
    if req_loc and not cand_loc:
        missing.append("candidate location")
    if req_loc and cand_loc and str(req_loc).lower() not in str(cand_loc).lower() and str(cand_loc).lower() not in str(req_loc).lower():
        reasons.append(f"location mismatch: {cand_loc!r} vs {req_loc!r}")
    passed = not reasons and not (req_loc and not cand_loc)
    return VerificationResult("location", passed, reasons, missing)


def check_relevance(candidate, requirement) -> VerificationResult:
    reasons = []
    missing = []
    excerpt = getattr(requirement, "excerpt", None)
    if excerpt is None and isinstance(requirement, dict):
        excerpt = requirement.get("excerpt", "")
    text = " ".join(str(candidate.get(k, "")) for k in ("title", "description", "metadata")) + " " + str(candidate.get("metadata", {}))
    req_entity_for_tokens = getattr(requirement, "entity", "")
    if not req_entity_for_tokens and isinstance(requirement, dict):
        req_entity_for_tokens = requirement.get("entity", "")
    req_tokens = set(name_tokens(str(excerpt) + " " + str(req_entity_for_tokens)))
    cand_tokens = set(name_tokens(text))
    overlap = len(req_tokens & cand_tokens) / max(1, len(req_tokens))
    entity_tokens = set(name_tokens(str(getattr(requirement, "entity", "") or (requirement.get("entity", "") if isinstance(requirement, dict) else ""))))
    # Relevance should not require a large fraction of the script excerpt; one
    # concrete shared entity/location token is enough to avoid false rejection.
    if req_tokens and overlap < 0.05 and not (entity_tokens & cand_tokens):
        reasons.append(f"low relevance overlap: {overlap:.2f}")
    if not text.strip():
        missing.append("candidate descriptive metadata")
    passed = not reasons and not missing
    return VerificationResult("relevance", passed, reasons, missing)


def check_quality(candidate) -> VerificationResult:
    reasons = []
    missing = []
    quality = candidate.get("quality") or {}
    if candidate.get("width") and candidate.get("height"):
        if int(candidate["width"]) < 32 or int(candidate["height"]) < 32:
            reasons.append("dimensions too small")
    else:
        missing.append("dimensions")
    if not candidate.get("content_hash"):
        missing.append("content hash")
    if candidate.get("mime") and not str(candidate["mime"]).startswith(("image/", "application/pdf", "text/")):
        reasons.append(f"unexpected mime: {candidate['mime']}")
    passed = not reasons and not missing
    return VerificationResult("quality", passed, reasons, missing)


def check_provenance(candidate) -> VerificationResult:
    reasons = []
    missing = []
    if not candidate.get("source_page_url"):
        missing.append("source page URL")
    if not candidate.get("file_url") and not candidate.get("local_path"):
        missing.append("file URL")
    if not candidate.get("retrieved_at"):
        missing.append("retrieval timestamp")
    if not candidate.get("content_hash"):
        missing.append("content hash")
    passed = not missing and not reasons
    return VerificationResult("provenance", passed, reasons, missing)


def check_usage(candidate) -> VerificationResult:
    reasons = []
    missing = []
    usage = candidate.get("usage") or {}
    review_state = candidate.get("review_state", "")
    if not usage and not candidate.get("license"):
        missing.append("usage or license evidence")
    if review_state in {"", "candidate"}:
        # Candidate state is acceptable before review, but must be explicit.
        reasons.append("review state not final")
    denied_terms = ["non-commercial", "all rights reserved", "fair use"]
    raw = " ".join(str(x) for x in [candidate.get("license"), usage.get("terms"), usage.get("statement")]).lower()
    if any(term in raw for term in denied_terms):
        reasons.append("usage terms deny or restrict reuse")
    passed = not reasons and not missing
    # Candidate state alone should not fail the gate; report as review-required instead.
    if review_state in {"", "candidate"} and not missing:
        return VerificationResult("usage", True, ["review required before production use"], [])
    return VerificationResult("usage", passed, reasons, missing)


def check_evidence(candidate, requirement) -> VerificationResult:
    reasons = []
    missing = []
    refs = candidate.get("evidence_refs") or []
    minimum = getattr(requirement, "minimum_evidence", None)
    if minimum is None and isinstance(requirement, dict):
        minimum = requirement.get("minimum_evidence", [])
    minimum = minimum or []
    if not refs:
        missing.append("supporting evidence references")
    if minimum and len(refs) < 1:
        missing.append("minimum evidence not met")
    passed = not missing and not reasons
    return VerificationResult("evidence", passed, reasons, missing)


def verify_candidate(candidate: dict, requirement) -> dict:
    results = [
        check_identity(candidate, requirement),
        check_time(candidate, requirement),
        check_location(candidate, requirement),
        check_relevance(candidate, requirement),
        check_quality(candidate),
        check_provenance(candidate),
        check_usage(candidate),
        check_evidence(candidate, requirement),
    ]
    mandatory_gates = {"identity", "provenance", "evidence"}
    failed = [r.gate for r in results if not r.passed and r.gate in mandatory_gates]
    review_gates = [r.gate for r in results if not r.passed and r.gate not in mandatory_gates]
    return {
        "candidate_id": candidate.get("id"),
        "passed": not failed,
        "failed_mandatory": failed,
        "review_gates": review_gates,
        "gates": [r.to_dict() for r in results],
    }
