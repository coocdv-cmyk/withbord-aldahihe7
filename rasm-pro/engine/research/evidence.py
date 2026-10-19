"""Evidence and research contracts for rasm-pro.

These dataclasses define the durable language of the research system.  They are
deliberately serialisable so that a research job can be interrupted, resumed and
audited without relying on model memory.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class AccessLevel(str, Enum):
    FULL_TEXT = "full_text"
    ABSTRACT = "abstract"
    SUMMARY = "summary"
    PREVIEW = "preview"
    METADATA_ONLY = "metadata_only"
    UNAVAILABLE = "unavailable"
    RESTRICTED = "restricted"
    UNKNOWN = "unknown"


class ReviewState(str, Enum):
    CANDIDATE = "candidate"
    REVIEW_REQUIRED = "review_required"
    APPROVED = "approved"
    REJECTED = "rejected"
    UNAVAILABLE = "unavailable"


class EvidenceKind(str, Enum):
    DIRECT = "direct"
    CONTEXTUAL = "contextual"
    ILLUSTRATION = "illustration"
    BROLL = "broll"


class RequirementStatus(str, Enum):
    OPEN = "open"
    RESEARCHING = "researching"
    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"
    FAILED = "failed"
    REVIEW_REQUIRED = "review_required"


@dataclass
class Chronology:
    raw: str = ""
    era: str = "unknown"          # CE | BCE | unknown
    start_year: int | None = None
    end_year: int | None = None
    precision: str = "unknown"     # exact | year | decade | century | range | unknown
    calendar: str = "gregorian"
    approximate: bool = False
    normalised: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ResearchBudget:
    max_seconds: float = 300.0
    max_requests: int = 40
    max_pages: int = 25
    max_downloads: int = 12
    max_download_bytes: int = 25_000_000
    max_depth: int = 2
    max_llm_calls: int = 12
    max_llm_tokens: int = 1200
    concurrency: int = 2
    resume: bool = True
    requests_used: int = 0
    pages_used: int = 0
    downloads_used: int = 0
    llm_calls_used: int = 0
    tokens_used: int = 0
    started_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class VerificationResult:
    gate: str
    passed: bool
    reasons: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ResearchRequirement:
    id: str
    scene_id: str
    unit_id: str
    excerpt: str
    purpose: str
    asset_type: str
    entity: str = ""
    alternative_names: list[str] = field(default_factory=list)
    time_context: str = ""
    location: str = ""
    edition: str = ""
    translator: str = ""
    publisher: str = ""
    collection: str = ""
    mandatory: list[str] = field(default_factory=list)
    optional: list[str] = field(default_factory=list)
    rejection: list[str] = field(default_factory=list)
    minimum_evidence: list[str] = field(default_factory=list)
    quality: dict[str, Any] = field(default_factory=dict)
    importance: str = "medium"
    priority: int = 50
    evidence_kind: str = EvidenceKind.CONTEXTUAL.value
    status: str = RequirementStatus.OPEN.value
    selected_asset_id: str | None = None
    notes: list[str] = field(default_factory=list)
    chronology: Chronology = field(default_factory=Chronology)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["chronology"] = self.chronology.to_dict()
        return d


@dataclass
class SourceAccess:
    url: str
    normalized_url: str = ""
    complete: bool = True
    resource_type: str = "unknown"
    access_level: str = AccessLevel.UNKNOWN.value
    retrieved_at: str = ""
    content_hash: str = ""
    byte_size: int = 0
    page_count: int = 0
    text_length: int = 0
    title: str = ""
    error: str = ""
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Evidence:
    id: str
    requirement_id: str
    source_url: str
    location: str = ""
    excerpt: str = ""
    kind: str = "supporting"        # supporting | contradicting | contextual
    confidence_note: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CandidateAsset:
    id: str
    requirement_ids: list[str] = field(default_factory=list)
    scene_ids: list[str] = field(default_factory=list)
    source_page_url: str = ""
    file_url: str = ""
    content_hash: str = ""
    retrieved_at: str = ""
    original_filename: str = ""
    mime: str = ""
    size_bytes: int = 0
    width: int | None = None
    height: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    entity: str = ""
    edition: str = ""
    time_context: str = ""
    location: str = ""
    quality: dict[str, Any] = field(default_factory=dict)
    usage: dict[str, Any] = field(default_factory=dict)
    evidence_refs: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    review_state: str = ReviewState.CANDIDATE.value
    ranking_features: dict[str, float] = field(default_factory=dict)
    ranking_score: float = 0.0
    derivatives: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ResearchClaim:
    id: str
    text: str
    claim_type: str = "general"
    source_url: str = ""
    location: str = ""
    representation: str = "verbatim"   # verbatim | translation | paraphrase | model_summary
    support: list[str] = field(default_factory=list)
    status: str = "unverified"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def requirement_from_dict(data: dict[str, Any]) -> ResearchRequirement:
    chronology = Chronology(**{k: v for k, v in (data.get("chronology") or {}).items() if k in Chronology.__dataclass_fields__})
    return ResearchRequirement(
        **{k: v for k, v in data.items() if k in ResearchRequirement.__dataclass_fields__ and k != "chronology"},
        chronology=chronology,
    )


def candidate_from_dict(data: dict[str, Any]) -> CandidateAsset:
    return CandidateAsset(**{k: v for k, v in data.items() if k in CandidateAsset.__dataclass_fields__})


def source_from_dict(data: dict[str, Any]) -> SourceAccess:
    return SourceAccess(**{k: v for k, v in data.items() if k in SourceAccess.__dataclass_fields__})


def evidence_from_dict(data: dict[str, Any]) -> Evidence:
    return Evidence(**{k: v for k, v in data.items() if k in Evidence.__dataclass_fields__})


def claim_from_dict(data: dict[str, Any]) -> ResearchClaim:
    return ResearchClaim(**{k: v for k, v in data.items() if k in ResearchClaim.__dataclass_fields__})


@dataclass
class ResearchState:
    job_id: str
    project: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))
    status: str = "created"
    requirements: list[ResearchRequirement] = field(default_factory=list)
    sources: list[SourceAccess] = field(default_factory=list)
    candidates: list[CandidateAsset] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    claims: list[ResearchClaim] = field(default_factory=list)
    queries: list[dict[str, Any]] = field(default_factory=list)
    visited_urls: list[str] = field(default_factory=list)
    decisions: list[dict[str, Any]] = field(default_factory=list)
    budget: ResearchBudget = field(default_factory=ResearchBudget)
    assistant_status: str = "not_checked"
    assistant_model: str = ""
    assistant_backend: str = ""
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "project": self.project,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "status": self.status,
            "requirements": [r.to_dict() for r in self.requirements],
            "sources": [s.to_dict() for s in self.sources],
            "candidates": [c.to_dict() for c in self.candidates],
            "evidence": [e.to_dict() for e in self.evidence],
            "claims": [c.to_dict() for c in self.claims],
            "queries": self.queries,
            "visited_urls": self.visited_urls,
            "decisions": self.decisions,
            "budget": self.budget.to_dict(),
            "assistant_status": self.assistant_status,
            "assistant_model": self.assistant_model,
            "assistant_backend": self.assistant_backend,
            "errors": self.errors,
            "warnings": self.warnings,
        }
