"""Stateful, iterative research workflow.

The workflow is intentionally bounded and resumable.  It records every query,
visited URL, candidate, gate result and decision so that an interrupted run can
continue without repeating work.
"""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..core.log import get_logger
from ..core.util import read_json, write_json
from ..stages.understanding import heuristic_script_graph, infer_needs
from .assistant import ResearchAssistant, load_assistant_config
from .discovery import DiscoveryRegistry, WikipediaDiscovery, WikidataDiscovery, CommonsDiscovery, LocalLibraryDiscovery
from .commons import Commons
from .evidence import (
    AccessLevel,
    Evidence,
    CandidateAsset,
    ResearchBudget,
    ResearchRequirement,
    ResearchState,
    SourceAccess,
    candidate_from_dict,
    evidence_from_dict,
    requirement_from_dict,
    source_from_dict,
)
from .identity import parse_chronology
from .readers import read_document
from .requirements import group_cues, parse_srt, requirements_from_script
from .urls import fetch_url, is_complete_url, is_safe_url
from .verification import verify_candidate

log = get_logger("research_workflow")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _job_id(payload: str) -> str:
    return "job-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


class ResearchWorkflow:
    def __init__(
        self,
        project_dir: Path,
        *,
        budget: ResearchBudget | None = None,
        assistant: ResearchAssistant | None = None,
        discovery: DiscoveryRegistry | None = None,
        http_client=None,
        store=None,
        download: bool = False,
        resume: bool = True,
    ):
        self.project_dir = Path(project_dir)
        self.budget = budget or ResearchBudget()
        if not self.budget.started_at:
            self.budget.started_at = _now()
        self.assistant = assistant if assistant is not None else ResearchAssistant(load_assistant_config())
        self.discovery = discovery
        self.http_client = http_client
        self.store = store
        self.download = download
        self.resume = resume
        self.state: ResearchState | None = None
        self._started_monotonic = time.monotonic()

    def _state_path(self) -> Path:
        return self.project_dir / "research" / "evidence_state.json"

    def _load_state(self, job_id: str) -> ResearchState | None:
        path = self._state_path()
        if not path.exists() or not self.resume:
            return None
        try:
            data = read_json(path, default={}) or {}
        except Exception:
            return None
        if data.get("job_id") != job_id:
            return None
        return ResearchState(
            job_id=data["job_id"],
            project=data.get("project", self.project_dir.name),
            created_at=data.get("created_at", _now()),
            updated_at=data.get("updated_at", _now()),
            status=data.get("status", "created"),
            requirements=[requirement_from_dict(x) for x in data.get("requirements", [])],
            sources=[source_from_dict(x) for x in data.get("sources", [])],
            candidates=[candidate_from_dict(x) for x in data.get("candidates", [])],
            evidence=[evidence_from_dict(x) for x in data.get("evidence", [])],
            claims=data.get("claims", []),
            queries=data.get("queries", []),
            visited_urls=data.get("visited_urls", []),
            decisions=data.get("decisions", []),
            budget=ResearchBudget(**{k: v for k, v in data.get("budget", {}).items() if k in ResearchBudget.__dataclass_fields__}),
            assistant_status=data.get("assistant_status", "not_checked"),
            assistant_model=data.get("assistant_model", ""),
            assistant_backend=data.get("assistant_backend", ""),
            errors=data.get("errors", []),
            warnings=data.get("warnings", []),
        )

    def _save_state(self) -> None:
        if self.state is None:
            return
        self.state.updated_at = _now()
        self.project_dir.joinpath("research").mkdir(parents=True, exist_ok=True)
        write_json(self._state_path(), self.state.to_dict())

    def _time_exhausted(self) -> bool:
        return (time.monotonic() - self._started_monotonic) >= self.budget.max_seconds

    def _budget_ok(self, *, request: bool = False, page: bool = False, download: bool = False, llm: bool = False) -> bool:
        if self._time_exhausted():
            return False
        if request and self.budget.requests_used >= self.budget.max_requests:
            return False
        if page and self.budget.pages_used >= self.budget.max_pages:
            return False
        if download and self.budget.downloads_used >= self.budget.max_downloads:
            return False
        if llm and self.budget.llm_calls_used >= self.budget.max_llm_calls:
            return False
        return True

    def _assistant_probe(self) -> None:
        if self.state is None:
            return
        status = self.assistant.probe()
        self.state.assistant_status = "available" if status.get("available") else status.get("error_type", "unavailable")
        self.state.assistant_model = status.get("model", "")
        self.state.assistant_backend = status.get("backend", "")
        if not status.get("available"):
            self.state.warnings.append(f"Language assistant unavailable: {status.get('error', '')}")

    def run(
        self,
        *,
        script_text: str | None = None,
        srt_text: str | None = None,
        graph: dict[str, Any] | None = None,
        source_urls: list[str] | None = None,
        local_documents: list[str] | None = None,
        language: str | None = None,
        download: bool | None = None,
    ) -> ResearchState:
        source_urls = source_urls or []
        local_documents = local_documents or []
        if download is not None:
            self.download = download

        # Build or reuse a script graph.
        if graph is None:
            if srt_text:
                cues = parse_srt(srt_text)
                units = group_cues(cues)
                all_text = " ".join(u["text"] for u in units)
                scenes = []
                for u in units:
                    scenes.append(
                        {
                            "id": u["unit_id"],
                            "narration": u["text"],
                            "duration": max(1.0, (u["end_seconds"] - u["start_seconds"]) or 5.0),
                            "needs": infer_needs(u["text"]),
                            "keywords": [],
                            "start": u["start"],
                            "end": u["end"],
                        }
                    )
                graph = {
                    "engine": "srt-heuristic",
                    "lang": language or ("ar" if _looks_arabic(all_text) else "en"),
                    "scenes": scenes,
                    "entities": _heuristic_entities(all_text),
                    "timeline": [],
                    "claims": [],
                    "stats": {"scenes": len(scenes), "words": len(all_text.split())},
                }
            else:
                script_text = script_text or ""
                graph = heuristic_script_graph(script_text)
                if language:
                    graph["lang"] = language

        if language:
            graph["lang"] = language

        requirements = requirements_from_script(graph)
        # Attach chronology already done in requirements; ensure time context parsed.
        for req in requirements:
            if not req.chronology.raw and req.time_context:
                req.chronology = parse_chronology(req.time_context)

        payload = json.dumps({"graph": graph, "urls": source_urls, "docs": local_documents}, sort_keys=True, ensure_ascii=False)
        job_id = _job_id(payload)
        state = self._load_state(job_id)
        if state is None:
            state = ResearchState(
                job_id=job_id,
                project=self.project_dir.name,
                status="created",
                requirements=requirements,
                budget=self.budget,
            )
        else:
            # Merge any new requirements while preserving completed ones.
            existing_ids = {r.id for r in state.requirements}
            for req in requirements:
                if req.id not in existing_ids:
                    state.requirements.append(req)
        self.state = state

        self._assistant_probe()

        if self.discovery is None:
            self.discovery = DiscoveryRegistry(
                [
                    WikipediaDiscovery(self.http_client) if self.http_client else WikipediaDiscovery(_default_http()),
                    WikidataDiscovery(self.http_client) if self.http_client else WikidataDiscovery(_default_http()),
                    CommonsDiscovery(self.http_client) if self.http_client else CommonsDiscovery(_default_http()),
                    LocalLibraryDiscovery(),
                ]
            )
        if self.http_client is None:
            self.http_client = _default_http()

        # Read user-provided sources first.
        for url in source_urls:
            self._read_source(url, requirement_ids=[])

        for doc in local_documents:
            self._read_local_document(doc)

        self.state.status = "researching"
        self._save_state()

        for req in list(self.state.requirements):
            if req.status in {"resolved", "failed"}:
                continue
            self._research_requirement(req)
            self._save_state()
            if self._time_exhausted():
                self.state.warnings.append("Research time budget exhausted; remaining requirements are unresolved.")
                break

        unresolved = [r for r in self.state.requirements if r.status not in {"resolved"}]
        self.state.status = "completed" if not unresolved else "completed_with_unresolved"
        self._save_state()
        self._write_outputs()
        return self.state

    def _research_requirement(self, req: ResearchRequirement) -> None:
        req.status = "researching"
        self._save_state()
        visited_queries = {(q.get("requirement_id"), q.get("query")) for q in self.state.queries}

        # Deterministic queries.
        queries = _deterministic_queries(req)
        # Bounded assistant help.
        if self.state.assistant_status == "available" and self._budget_ok(llm=True):
            try:
                self.budget.llm_calls_used += 1
                data = self.assistant.draft_queries(req.to_dict())
                for item in data.get("queries", []) or []:
                    if isinstance(item, dict) and item.get("query"):
                        queries.append(str(item["query"]))
                    elif isinstance(item, str):
                        queries.append(item)
            except Exception as exc:
                self.state.warnings.append(f"Assistant query drafting failed for {req.id}: {exc}")

        # De-duplicate while preserving order.
        unique_queries = []
        for q in queries:
            key = (req.id, q.strip())
            if q.strip() and key not in visited_queries:
                unique_queries.append(q.strip())
                visited_queries.add(key)

        for query in unique_queries:
            if not self._budget_ok(request=True):
                req.notes.append("request budget exhausted")
                break
            if self._time_exhausted():
                req.notes.append("time budget exhausted")
                break
            self.budget.requests_used += 1
            self.state.queries.append({"requirement_id": req.id, "query": query, "at": _now()})
            results = self.discovery.search_all(query, limit=8)
            results.sort(key=lambda r: 0 if (r.get('provider') == 'wikimedia_commons' or str(r.get('title','')).startswith('File:')) else 1)
            for raw_result in results:
                result = dict(raw_result)
                title = str(result.get("title") or "")
                if result.get("provider") == "wikimedia_commons" or title.startswith("File:"):
                    try:
                        infos = Commons(self.http_client).file_info([title], thumb_width=1600)
                        if infos:
                            info = infos[0]
                            result.update(info)
                            result["page_url"] = info.get("page_url") or result.get("url")
                            result["provider"] = "wikimedia_commons"
                    except Exception:
                        pass
                url = result.get("url") or result.get("page_url")
                if not url or not is_complete_url(url):
                    continue
                if url in self.state.visited_urls:
                    continue
                if not self._budget_ok(page=True):
                    req.notes.append("page budget exhausted")
                    break
                self.budget.pages_used += 1
                self.state.visited_urls.append(url)
                access, data = fetch_url(url, timeout=20, max_bytes=4_000_000, user_agent=self.http_client.ua if self.http_client else "rasm-pro")
                self.state.sources.append(access)
                document = read_document(access, data)
                # Candidate creation for image-like results.
                if access.resource_type == "image" or str(result.get("title", "")).lower().endswith((".jpg", ".png", ".svg", ".webp")):
                    self._create_candidate(req, result, access, data, document)
                # Follow a small number of relevant links if budget allows.
                for link in (document.get("links") or [])[:3]:
                    if not is_complete_url(link):
                        continue
                    # Only follow links that look relevant to the requirement.
                    if not _link_relevant(link, req):
                        continue
                    if link in self.state.visited_urls or not self._budget_ok(page=True):
                        continue
                    self.budget.pages_used += 1
                    self.state.visited_urls.append(link)
                    la, ld = fetch_url(link, timeout=20, max_bytes=2_000_000, user_agent=self.http_client.ua if self.http_client else "rasm-pro")
                    self.state.sources.append(la)
                    read_document(la, ld)
            # After processing query, evaluate requirement.
            if self._requirement_resolved(req):
                req.status = "resolved"
                return
        if not self._requirement_resolved(req):
            req.status = "unresolved"
            req.notes.append("No candidate passed all mandatory verification gates.")

    def _create_candidate(self, req, result, access, data, document) -> None:
        candidate_id = "cand-" + hashlib.sha256((access.normalized_url or access.url).encode("utf-8")).hexdigest()[:12]
        if any(c.id == candidate_id for c in self.state.candidates):
            return
        quality = _image_quality(data)
        usage = {
            "license": result.get("license"),
            "license_url": result.get("license_url"),
            "terms": result.get("permission") or result.get("usage_terms"),
            "statement": result.get("credit") or result.get("description"),
        }
        candidate = CandidateAsset(
            id=candidate_id,
            requirement_ids=[req.id],
            scene_ids=[req.scene_id],
            source_page_url=result.get("page_url") or access.normalized_url or access.url,
            file_url=access.normalized_url or access.url,
            content_hash=access.content_hash,
            retrieved_at=access.retrieved_at,
            original_filename=result.get("title", ""),
            mime=access.resource_type and ("image/" + access.resource_type if access.resource_type != "image" else "image/unknown"),
            size_bytes=access.byte_size,
            width=quality.get("width"),
            height=quality.get("height"),
            metadata={
                "title": result.get("title", ""),
                "description": result.get("description", "") or document.get("text", "")[:500],
                "provider": result.get("provider", ""),
                "entity": req.entity,
            },
            entity=req.entity,
            edition=req.edition,
            time_context=req.time_context,
            location=req.location,
            quality=quality,
            usage=usage,
            evidence_refs=[],
            review_state="candidate",
        )
        # Download if requested and store available.
        if self.download and self.store is not None and self._budget_ok(download=True):
            try:
                self.budget.downloads_used += 1
                rec = self.store.download(candidate.file_url, kind=req.asset_type, subdir=f"{req.scene_id}-{req.entity[:24]}", mime=candidate.mime, record_meta={
                    "title": candidate.metadata.get("title"),
                    "entity": req.entity,
                    "need": req.asset_type,
                    "requirement_id": req.id,
                })
                if rec:
                    candidate.content_hash = rec.get("sha256", candidate.content_hash)
                    candidate.metadata["stored_path"] = rec.get("path")
            except Exception as exc:
                candidate.issues.append(f"download failed: {exc}")

        # Add evidence reference for the source access.
        ev_id = "ev-" + candidate.id
        self.state.evidence.append(Evidence(
            id=ev_id,
            requirement_id=req.id,
            source_url=candidate.source_page_url,
            location="",
            excerpt=(document.get("text") or "")[:300],
            kind="supporting",
            confidence_note="source metadata and deterministic checks only",
        ))
        candidate.evidence_refs.append(ev_id)

        verification = verify_candidate(candidate.to_dict(), req)
        candidate.issues.extend(verification["failed_mandatory"] + verification["review_gates"])
        # Ranking features are documented, not a probability.
        candidate.ranking_features = {
            "identity_gate": 1.0 if "identity" not in verification["failed_mandatory"] + verification["review_gates"] else 0.0,
            "provenance_gate": 1.0 if "provenance" not in verification["failed_mandatory"] + verification["review_gates"] else 0.0,
            "quality_gate": 1.0 if "quality" not in verification["failed_mandatory"] + verification["review_gates"] else 0.0,
        }
        candidate.ranking_score = sum(candidate.ranking_features.values()) / max(1, len(candidate.ranking_features))
        if verification["passed"]:
            candidate.review_state = "review_required"
        self.state.candidates.append(candidate)

    def _requirement_resolved(self, req: ResearchRequirement) -> bool:
        linked = [c for c in self.state.candidates if req.id in (c.requirement_ids or [])]
        return any(c.review_state in {"review_required", "approved"} and not any(g in c.issues for g in ["identity"]) for c in linked)

    def _read_source(self, url: str, requirement_ids: list[str]) -> None:
        if not is_complete_url(url):
            if self.state:
                self.state.warnings.append(f"Incomplete URL skipped: {url}")
            return
        safe, reason = is_safe_url(url)
        if not safe:
            if self.state:
                self.state.warnings.append(f"Unsafe URL skipped ({reason}): {url}")
            return
        if url in (self.state.visited_urls if self.state else []):
            return
        if self.state:
            self.state.visited_urls.append(url)
        if not self._budget_ok(page=True):
            return
        self.budget.pages_used += 1
        access, data = fetch_url(url, timeout=20, max_bytes=5_000_000, user_agent=self.http_client.ua if self.http_client else "rasm-pro")
        if self.state:
            self.state.sources.append(access)
        read_document(access, data)

    def _read_local_document(self, path: str) -> None:
        p = Path(path)
        if not p.exists():
            if self.state:
                self.state.warnings.append(f"Local document not found: {path}")
            return
        # Represent as a source access with file URL.
        access = SourceAccess(url=str(p), normalized_url=str(p), complete=True, resource_type=_resource_type_for_path(p),
                             access_level=AccessLevel.FULL_TEXT.value, retrieved_at=_now(), byte_size=p.stat().st_size,
                             content_hash=_sha256_file(p))
        if self.state:
            self.state.sources.append(access)

    def _write_outputs(self) -> None:
        if self.state is None:
            return
        out_dir = self.project_dir / "research"
        out_dir.mkdir(parents=True, exist_ok=True)
        write_json(out_dir / "evidence.json", self.state.to_dict())
        # Compatibility summary for the existing pipeline.
        summary = {
            "generated_at": _now(),
            "project": self.project_dir.name,
            "assistant_status": self.state.assistant_status,
            "requirements_total": len(self.state.requirements),
            "requirements_resolved": sum(1 for r in self.state.requirements if r.status == "resolved"),
            "requirements_unresolved": sum(1 for r in self.state.requirements if r.status != "resolved"),
            "candidates_total": len(self.state.candidates),
            "sources_total": len(self.state.sources),
            "budget": self.state.budget.to_dict(),
        }
        write_json(out_dir / "evidence_summary.json", summary)


def _default_http():
    from .http import HttpClient

    return HttpClient("rasm-pro research (local)", timeout=20)


def _looks_arabic(text: str) -> bool:
    import re

    return bool(re.search(r"[\u0600-\u06ff]", text or ""))


def _heuristic_entities(text: str) -> list[dict[str, Any]]:
    try:
        from ..stages.understanding import heuristic_entities

        return heuristic_entities(text)
    except Exception:
        return []


def _deterministic_queries(req: ResearchRequirement) -> list[str]:
    queries = []
    if req.entity:
        queries.append(req.entity)
        for alt in req.alternative_names:
            queries.append(alt)
    if req.asset_type == "document":
        queries.append(f"{req.entity} title page".strip())
    if req.asset_type == "map":
        queries.append(f"{req.entity} map".strip())
    if req.location:
        queries.append(f"{req.entity} {req.location}".strip())
    # Remove empty and de-duplicate.
    out = []
    seen = set()
    for q in queries:
        q = " ".join(q.split())
        if q and q not in seen:
            seen.add(q)
            out.append(q)
    return out[:6]


def _link_relevant(link: str, req: ResearchRequirement) -> bool:
    low = link.lower()
    if any(x in low for x in ("login", "signup", "privacy", "terms", "javascript:")):
        return False
    tokens = set((req.entity or "").lower().split())
    return any(tok in low for tok in tokens if len(tok) > 3) or req.asset_type in low


def _image_quality(data: bytes) -> dict[str, Any]:
    try:
        from PIL import Image
        import io

        img = Image.open(io.BytesIO(data))
        img.verify()
        img = Image.open(io.BytesIO(data))
        return {"decoded": True, "width": img.width, "height": img.height, "format": img.format}
    except Exception as exc:
        return {"decoded": False, "width": None, "height": None, "error": str(exc)}


def _resource_type_for_path(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return "pdf"
    if suffix in {".epub"}:
        return "epub"
    if suffix in {".jpg", ".jpeg", ".png", ".webp", ".svg", ".tif", ".tiff"}:
        return "image"
    if suffix in {".html", ".htm"}:
        return "html"
    if suffix == ".json":
        return "json"
    return "unknown"


def _sha256_file(path: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()
