"""Asset identity, human approval and the production render gate.

Stage 3 contract
----------------
* Every asset has a **stable id** derived from its content hash
  (``a-<sha256[:12]>``).  The id survives moving a project folder.
* The plan references assets by ``asset_id`` (preferred) or by a project
  relative path.  The manifest stays the registry of assets.
* Every approval decision is written to an **append-only log**
  (``research/approvals.jsonl``).  The manifest is only a projection of it.
* A **final** render refuses any asset that is not approved, has no license,
  has no origin, or was rejected.  A **preview** render may pass unapproved
  assets but says so loudly and refuses rejected ones in every mode.

Nothing here downloads anything, calls a model, or approves on the owner's
behalf.  Generated artwork is never treated as historical evidence.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .project import ProjectError, relative_project_path

__all__ = [
    "APPROVALS_FILE",
    "DECISIONS",
    "MODES",
    "ApprovalError",
    "AssetRef",
    "GateReport",
    "append_decision",
    "asset_id_for",
    "decisions_by_asset",
    "evaluate_gate",
    "latest_decision",
    "link_plan_assets",
    "load_decisions",
    "plan_asset_refs",
    "sync_manifest_approvals",
]

APPROVALS_FILE = "research/approvals.jsonl"
DECISIONS = ("approved", "rejected", "deferred")
MODES = ("final", "preview")


class ApprovalError(ValueError):
    """Invalid approval input or an unusable decision log."""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# --------------------------------------------------------------------------
# identity
# --------------------------------------------------------------------------
def asset_id_for(sha256: str | None, relative_path: str) -> str:
    """Stable asset id.

    The content hash is preferred because it identifies the *bytes*; the path
    is only a fallback for assets that were never hashed.
    """
    if sha256:
        clean = str(sha256).strip().lower()
        if len(clean) >= 12:
            return "a-" + clean[:12]
    digest = hashlib.sha256(str(relative_path).replace("\\", "/").encode("utf-8")).hexdigest()
    return "a-" + digest[:12]


def _relative(project_dir: str | Path, raw: str | Path) -> str | None:
    """Project relative POSIX path, or ``None`` when the path escapes the project."""
    try:
        return relative_project_path(project_dir, raw)
    except ProjectError:
        return None


# --------------------------------------------------------------------------
# decision log (append only)
# --------------------------------------------------------------------------
@dataclass
class Decision:
    asset_id: str
    path: str
    decision: str
    reviewer: str
    reviewed_at: str
    note: str = ""
    license: str = ""
    source: str = ""
    origin_url: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def approvals_path(project_dir: str | Path) -> Path:
    return Path(project_dir) / APPROVALS_FILE


def load_decisions(project_dir: str | Path) -> list[dict]:
    """Read the append-only decision log.  A broken line is reported, not hidden."""
    p = approvals_path(project_dir)
    if not p.exists():
        return []
    out: list[dict] = []
    for number, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ApprovalError(f"سجل القرارات تالف في السطر {number}: {exc}") from exc
        if not isinstance(rec, dict):
            raise ApprovalError(f"سجل القرارات: سطر {number} ليس كائنًا")
        out.append(rec)
    return out


def append_decision(
    project_dir: str | Path,
    *,
    asset_id: str,
    path: str,
    decision: str,
    reviewer: str,
    note: str = "",
    license: str = "",
    source: str = "",
    origin_url: str = "",
    reviewed_at: str | None = None,
) -> dict:
    """Append one human decision to the log and return the stored record."""
    decision = str(decision).strip().lower()
    if decision not in DECISIONS:
        raise ApprovalError(f"قرار غير معروف: {decision!r} (المتاح: {', '.join(DECISIONS)})")
    reviewer = str(reviewer).strip()
    if not reviewer:
        raise ApprovalError("لا بد من اسم المراجع (من {})".format("--by"))
    asset_id = str(asset_id).strip()
    if not asset_id:
        raise ApprovalError("لا بد من معرّف الأصل")
    rec = {
        "asset_id": asset_id,
        "path": str(path).replace("\\", "/"),
        "decision": decision,
        "reviewer": reviewer,
        "reviewed_at": reviewed_at or utc_now(),
        "note": str(note or ""),
        "license": str(license or ""),
        "source": str(source or ""),
        "origin_url": str(origin_url or ""),
    }
    p = approvals_path(project_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())
    return rec


def decisions_by_asset(project_dir: str | Path) -> dict[str, list[dict]]:
    """All decisions grouped by asset id, oldest first."""
    grouped: dict[str, list[dict]] = {}
    for rec in load_decisions(project_dir):
        grouped.setdefault(str(rec.get("asset_id") or ""), []).append(rec)
    return grouped


def latest_decision(project_dir: str | Path, asset_id: str) -> dict | None:
    records = decisions_by_asset(project_dir).get(asset_id) or []
    return records[-1] if records else None


# --------------------------------------------------------------------------
# plan references
# --------------------------------------------------------------------------
@dataclass
class AssetRef:
    asset_id: str
    path: str                      # project relative POSIX path ("" when unknown)
    display: str                   # the raw reference as written in the plan
    scenes: list[str] = field(default_factory=list)
    elements: list[str] = field(default_factory=list)
    as_evidence: bool = False
    exists: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def _element_key(scene_id: Any, index: int) -> str:
    return f"{scene_id}#{index}"


def plan_asset_refs(
    plan: dict,
    project_dir: str | Path,
    *,
    manifest: dict | None = None,
) -> list[AssetRef]:
    """Every asset the plan refers to, with the scenes/elements that use it.

    References are accepted as ``asset_id`` or as a path (absolute inside the
    project or relative).  Absolute paths are normalised back to project
    relative paths so a moved project keeps working.
    """
    root = Path(project_dir).resolve()
    by_path: dict[str, dict] = {}
    by_id: dict[str, dict] = {}
    for entry in (manifest or {}).get("assets") or []:
        if not isinstance(entry, dict):
            continue
        rel = str(entry.get("path") or "").replace("\\", "/")
        if rel:
            by_path[rel] = entry
        aid = str(entry.get("asset_id") or "")
        if aid:
            by_id[aid] = entry

    refs: dict[str, AssetRef] = {}

    def ensure(asset_id: str, path: str, display: str) -> AssetRef:
        key = asset_id or f"path:{path}"
        ref = refs.get(key)
        if ref is None:
            ref = AssetRef(asset_id=asset_id, path=path, display=display)
            refs[key] = ref
        return ref

    def resolve(raw: str) -> tuple[str, str]:
        """(asset_id, relative path) for a raw plan reference."""
        raw = str(raw)
        entry = None
        if raw in by_id:
            entry = by_id[raw]
            rel = str(entry.get("path") or "").replace("\\", "/")
            return str(entry.get("asset_id") or raw), rel
        rel = _relative(root, raw) if raw else None
        if rel is None:
            return "", ""
        entry = by_path.get(rel)
        if entry is not None:
            return str(entry.get("asset_id") or asset_id_for(entry.get("sha256"), rel)), rel
        return asset_id_for(None, rel), rel

    for scene in plan.get("scenes") or []:
        if not isinstance(scene, dict):
            continue
        scene_id = str(scene.get("id", "?"))
        scene_evidence = bool(scene.get("evidence"))
        for raw in scene.get("assets_used") or []:
            aid, rel = resolve(str(raw))
            ref = ensure(aid, rel, str(raw))
            if scene_id not in ref.scenes:
                ref.scenes.append(scene_id)
            ref.as_evidence = ref.as_evidence or scene_evidence
        for index, element in enumerate(scene.get("elements") or []):
            if not isinstance(element, dict):
                continue
            raw = element.get("asset")
            if not raw:
                continue
            aid, rel = resolve(str(raw))
            ref = ensure(aid, rel, str(raw))
            key = _element_key(scene_id, index)
            if key not in ref.elements:
                ref.elements.append(key)
            if scene_id not in ref.scenes:
                ref.scenes.append(scene_id)
            ref.as_evidence = ref.as_evidence or bool(element.get("evidence"))

    for ref in refs.values():
        ref.exists = bool(ref.path) and (root / ref.path).exists()
    return [refs[k] for k in sorted(refs)]


# --------------------------------------------------------------------------
# the gate
# --------------------------------------------------------------------------
@dataclass
class GateReport:
    mode: str
    ok: bool
    used: list[dict] = field(default_factory=list)
    blocking: list[dict] = field(default_factory=list)
    warnings: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _manifest_assets(manifest: dict | None) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for entry in (manifest or {}).get("assets") or []:
        if not isinstance(entry, dict):
            continue
        rel = str(entry.get("path") or "").replace("\\", "/")
        if rel:
            out[rel] = entry
    return out


def evaluate_gate(
    plan: dict,
    project_dir: str | Path,
    *,
    manifest: dict | None = None,
    mode: str = "final",
) -> GateReport:
    """Decide whether the plan may be rendered in ``mode``.

    ``final``   - production output: unapproved, unlicensed or unidentified
                  assets block the render.
    ``preview`` - a look at the storyboard: unapproved assets are allowed but
                  reported; a *rejected* asset blocks in every mode.
    """
    mode = str(mode or "final").strip().lower()
    if mode not in MODES:
        raise ApprovalError(f"وضع غير معروف: {mode!r} (المتاح: {', '.join(MODES)})")

    assets = _manifest_assets(manifest)
    decisions = decisions_by_asset(project_dir)
    report = GateReport(mode=mode, ok=True)

    for ref in plan_asset_refs(plan, project_dir, manifest=manifest):
        entry = assets.get(ref.path) if ref.path else None
        decision = (decisions.get(ref.asset_id) or [None])[-1] if ref.asset_id else None
        state = str((decision or {}).get("decision") or "pending")
        license_name = ""
        origin_kind = ""
        if entry is not None:
            license_name = str((entry.get("license") or {}).get("name") or "")
            origin_kind = str((entry.get("origin") or {}).get("kind") or "")
        generated = origin_kind.strip().lower() in {"generated", "synthetic", "ai"}

        item = {
            "asset_id": ref.asset_id,
            "path": ref.path,
            "display": ref.display,
            "scenes": ref.scenes,
            "elements": ref.elements,
            "state": state,
            "license": license_name,
            "origin": origin_kind,
            "generated": generated,
            "reviewer": str((decision or {}).get("reviewer") or ""),
        }
        report.used.append(item)

        def block(reason: str, detail: str = "") -> None:
            report.ok = False
            report.blocking.append({**item, "reason": reason, "detail": detail})

        def warn(reason: str, detail: str = "") -> None:
            report.warnings.append({**item, "reason": reason, "detail": detail})

        if not ref.path:
            block("asset-outside-project", f"المسار خارج المشروع: {ref.display}")
            continue
        if not ref.exists:
            block("asset-missing", f"الملف غير موجود: {ref.path}")
            continue
        if entry is None:
            reason = "asset-not-registered"
            detail = "الأصل غير مسجّل في المانيفست (لا مصدر ولا ترخيص)"
            block(reason, detail) if mode == "final" else warn(reason, detail)
            continue
        if state == "rejected":
            block(
                "asset-rejected",
                f"الأصل مرفوض{': ' + str((decision or {}).get('note') or '') if (decision or {}).get('note') else ''}",
            )
            continue
        if state == "approved":
            if not license_name or license_name.upper() == "UNKNOWN":
                reason = "asset-license-missing"
                detail = "لا يوجد ترخيص مسجّل للأصل"
                block(reason, detail) if mode == "final" else warn(reason, detail)
            if not origin_kind:
                reason = "asset-origin-missing"
                detail = "لا يوجد مصدر (origin) مسجّل للأصل"
                block(reason, detail) if mode == "final" else warn(reason, detail)
        else:
            reason = "asset-not-approved"
            detail = f"الأصل بحالة '{state}' ويحتاج موافقة بشرية"
            block(reason, detail) if mode == "final" else warn(reason, detail)
        if generated and ref.as_evidence:
            block(
                "generated-as-evidence",
                "الصورة المولَّدة لا تُستخدم كدليل تاريخي",
            )
        elif generated:
            warn("generated-asset", "أصل مولَّد (ليس دليلًا) — تحقّق من أنه توصيفي وليس إثباتًا")

    return report


# --------------------------------------------------------------------------
# plan linking
# --------------------------------------------------------------------------
def link_plan_assets(
    plan: dict,
    project_dir: str | Path,
    *,
    manifest: dict | None = None,
) -> tuple[dict, list[dict]]:
    """Rewrite the plan's asset references into project relative + ``asset_id``.

    The plan is copied, never mutated in place.  The returned change list
    describes every rewrite so the caller can log and verify it.
    """
    root = Path(project_dir).resolve()
    out = json.loads(json.dumps(plan, ensure_ascii=False))
    by_path: dict[str, dict] = {}
    by_id: dict[str, dict] = {}
    for entry in (manifest or {}).get("assets") or []:
        if not isinstance(entry, dict):
            continue
        rel = str(entry.get("path") or "").replace("\\", "/")
        if rel:
            by_path[rel] = entry
        aid = str(entry.get("asset_id") or "")
        if aid:
            by_id[aid] = entry

    changes: list[dict] = []

    def convert(raw: str) -> tuple[str, str]:
        """(relative path, asset_id) for a raw reference."""
        raw = str(raw)
        if raw in by_id:
            entry = by_id[raw]
            rel = str(entry.get("path") or "").replace("\\", "/")
            return rel, str(entry.get("asset_id") or raw)
        rel = _relative(root, raw) or ""
        entry = by_path.get(rel)
        if entry is not None:
            return rel, str(entry.get("asset_id") or asset_id_for(entry.get("sha256"), rel))
        return rel, asset_id_for(None, rel)

    for scene in out.get("scenes") or []:
        if not isinstance(scene, dict):
            continue
        scene_ids: list[str] = []
        used: list[str] = []
        for raw in scene.get("assets_used") or []:
            rel, aid = convert(raw)
            if rel != str(raw):
                changes.append({"scene": scene.get("id"), "field": "assets_used", "from": str(raw), "to": rel})
            if rel and rel not in used:
                used.append(rel)
            if aid and aid not in scene_ids:
                scene_ids.append(aid)
        if used:
            scene["assets_used"] = used
        elif "assets_used" in scene:
            scene["assets_used"] = []
        for index, element in enumerate(scene.get("elements") or []):
            if not isinstance(element, dict):
                continue
            raw = element.get("asset")
            if not raw:
                continue
            rel, aid = convert(str(raw))
            if rel != str(raw):
                changes.append(
                    {
                        "scene": scene.get("id"),
                        "field": f"elements[{index}].asset",
                        "from": str(raw),
                        "to": rel,
                    }
                )
            if rel:
                element["asset"] = rel
            if aid:
                element["asset_id"] = aid
                if aid not in scene_ids:
                    scene_ids.append(aid)
        if scene_ids:
            scene["asset_ids"] = sorted(scene_ids)
    return out, changes


# --------------------------------------------------------------------------
# manifest projection
# --------------------------------------------------------------------------
def sync_manifest_approvals(manifest: dict, project_dir: str | Path) -> dict:
    """Project the decision log into the manifest (pure function)."""
    if not isinstance(manifest, dict):
        raise ApprovalError("المانيفست يجب أن يكون كائنًا JSON")
    out = json.loads(json.dumps(manifest, ensure_ascii=False))
    grouped = decisions_by_asset(project_dir)
    pending = 0
    approved = 0
    rejected = 0
    for entry in out.get("assets") or []:
        if not isinstance(entry, dict):
            continue
        rel = str(entry.get("path") or "").replace("\\", "/")
        aid = str(entry.get("asset_id") or "") or asset_id_for(entry.get("sha256"), rel)
        entry["asset_id"] = aid
        records = grouped.get(aid) or []
        last = records[-1] if records else None
        state = str((last or {}).get("decision") or "pending")
        if state == "approved":
            approved += 1
        elif state == "rejected":
            rejected += 1
        else:
            pending += 1
        entry["approval"] = {
            "decision": state,
            "reviewer": str((last or {}).get("reviewer") or ""),
            "reviewed_at": str((last or {}).get("reviewed_at") or ""),
            "note": str((last or {}).get("note") or ""),
            "records": len(records),
        }
        if state == "approved":
            entry["approved_by"] = str((last or {}).get("reviewer") or "") or None
            entry["approved_at"] = str((last or {}).get("reviewed_at") or "") or None
        else:
            entry["approved_by"] = None
            entry["approved_at"] = None

    policy = out.get("asset_policy")
    if not isinstance(policy, dict):
        policy = {}
    policy.setdefault("requires_origin", True)
    policy.setdefault("requires_license", True)
    policy.setdefault("retrieved_requires_approval", True)
    policy.setdefault("generated_is_evidence", False)
    policy["final_render_requires_approval"] = True
    out["asset_policy"] = policy

    log_path = approvals_path(project_dir)
    records = load_decisions(project_dir)
    out["approval_log"] = {
        "path": APPROVALS_FILE,
        "records": len(records),
        "sha256": hashlib.sha256(log_path.read_bytes()).hexdigest() if log_path.exists() else "",
    }

    unresolved = [u for u in (out.get("unresolved") or []) if isinstance(u, dict)]
    found = False
    for item in unresolved:
        if item.get("id") == "assets-pending-approval":
            found = True
            item["message"] = (
                f"{pending} أصلًا بانتظار الاعتماد البشري"
                f" (معتمد: {approved} · مرفوض: {rejected}) قبل الإنتاج."
            )
            item["blocking"] = pending > 0
            item["counts"] = {"pending": pending, "approved": approved, "rejected": rejected}
    if not found and (pending or approved or rejected):
        unresolved.append(
            {
                "id": "assets-pending-approval",
                "kind": "assets",
                "blocking": pending > 0,
                "message": (
                    f"{pending} أصلًا بانتظار الاعتماد البشري"
                    f" (معتمد: {approved} · مرفوض: {rejected}) قبل الإنتاج."
                ),
                "counts": {"pending": pending, "approved": approved, "rejected": rejected},
            }
        )
    out["unresolved"] = unresolved
    return out
