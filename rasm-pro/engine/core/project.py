"""Project manifest contract (``project.json``).

The manifest is the project's entry point.  It stores identity, the active
storyboard and hashes of the files that matter; it never copies their content.
All paths are relative to the project directory and are rejected if they try to
escape it.

The writer is atomic (same-directory temporary file + ``os.replace``), and the
validator checks hashes rather than timestamps, so a project can be moved or
restored without pretending that dates prove integrity.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .timebase import TimebaseError, coerce_frame_rate, frame_rate_json
from .util import read_json, sha256_file

__all__ = [
    "MANIFEST_NAME",
    "SCHEMA_VERSION",
    "ProjectError",
    "project_manifest_path",
    "read_manifest",
    "write_manifest",
    "resolve_project_path",
    "relative_project_path",
    "load_active_plan",
    "manifest_plan_path",
    "activate_plan",
    "infer_manifest",
    "validate_manifest",
    "utc_now",
]

MANIFEST_NAME = "project.json"
SCHEMA_VERSION = "1.0"
STATUSES = ("draft", "researched", "planned", "approved", "rendered")
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")


class ProjectError(ValueError):
    """Invalid project manifest or unsafe project path."""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def project_manifest_path(project_dir: str | Path) -> Path:
    return Path(project_dir) / MANIFEST_NAME


def _project_root(project_dir: str | Path) -> Path:
    root = Path(project_dir).resolve()
    if not root.exists() or not root.is_dir():
        raise ProjectError(f"مجلد المشروع غير موجود: {root}")
    return root


def resolve_project_path(project_dir: str | Path, value: str | Path, *, must_exist: bool = False) -> Path:
    """Resolve a manifest path, rejecting absolute paths and ``..`` escapes."""
    root = _project_root(project_dir)
    raw = Path(value)
    if raw.is_absolute():
        raise ProjectError(f"مسار مطلق في المانيفست (يجب أن يكون نسبيًا): {value}")
    p = (root / raw).resolve()
    if p != root and root not in p.parents:
        raise ProjectError(f"مسار يخرج من مجلد المشروع: {value}")
    if must_exist and not p.exists():
        raise ProjectError(f"مسار مشار إليه غير موجود: {value}")
    return p


def relative_project_path(project_dir: str | Path, value: str | Path) -> str:
    root = _project_root(project_dir)
    p = Path(value)
    if not p.is_absolute():
        p = root / p
    p = p.resolve()
    try:
        rel = p.relative_to(root)
    except ValueError as exc:
        raise ProjectError(f"لا يمكن التعبير عن المسار داخل المشروع: {value}") from exc
    return rel.as_posix()


def read_manifest(project_dir: str | Path, *, required: bool = False) -> dict | None:
    p = project_manifest_path(project_dir)
    if not p.exists():
        if required:
            raise ProjectError(f"لا يوجد مانيفست مشروع: {p}")
        return None
    try:
        data = read_json(p)
    except Exception as exc:
        raise ProjectError(f"مانيفست غير قابل للقراءة: {p}: {exc}") from exc
    if not isinstance(data, dict):
        raise ProjectError(f"مانيفست المشروع يجب أن يكون كائنًا JSON: {p}")
    return data


def write_manifest(project_dir: str | Path, manifest: dict) -> Path:
    """Atomically write ``project.json`` (UTF-8, stable ordering from the caller)."""
    if not isinstance(manifest, dict):
        raise ProjectError("المانيفست يجب أن يكون كائنًا JSON")
    p = project_manifest_path(project_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(manifest, ensure_ascii=False, indent=2)
    fd, tmp_name = tempfile.mkstemp(prefix=".project-", suffix=".tmp", dir=str(p.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, p)
    finally:
        try:
            Path(tmp_name).unlink()
        except FileNotFoundError:
            pass
    return p


def _safe_rel(project_dir: Path, value: Any) -> str | None:
    if not isinstance(value, (str, Path)) or not str(value).strip():
        return None
    try:
        return relative_project_path(project_dir, value)
    except ProjectError:
        return None


def manifest_plan_path(project_dir: str | Path, manifest: dict | None = None) -> Path:
    pd = Path(project_dir)
    man = manifest if manifest is not None else read_manifest(pd, required=True)
    assert man is not None
    active = (man.get("storyboard") or {}).get("active")
    if not active:
        raise ProjectError("storyboard.active غير معلن في المانيفست")
    return resolve_project_path(pd, active, must_exist=True)


def load_active_plan(
    project_dir: str | Path,
    manifest: dict | None = None,
    *,
    verify_hash: bool = True,
) -> tuple[dict, Path]:
    pd = Path(project_dir)
    man = manifest if manifest is not None else read_manifest(pd, required=True)
    assert man is not None
    path = manifest_plan_path(pd, man)
    try:
        plan = read_json(path)
    except Exception as exc:
        raise ProjectError(f"الخطة النشطة غير قابلة للقراءة: {path}: {exc}") from exc
    if not isinstance(plan, dict):
        raise ProjectError(f"الخطة النشطة يجب أن تكون كائنًا JSON: {path}")
    expected = (man.get("storyboard") or {}).get("sha256")
    if verify_hash and expected:
        actual = sha256_file(path)
        if actual.lower() != str(expected).lower():
            raise ProjectError(
                f"هاش الخطة النشطة لا يطابق المانيفست: {actual} != {expected}"
            )
    return plan, path


def activate_plan(project_dir: str | Path, plan_path: str | Path) -> Path:
    """Point the manifest at a plan and refresh its hash/rate after a rebuild."""
    pd = Path(project_dir)
    man = read_manifest(pd, required=True)
    assert man is not None
    raw = Path(plan_path)
    if raw.is_absolute():
        # Callers often pass the just-saved absolute path.  Normalize it, but
        # never let an absolute path outside the project become active.
        raw = relative_project_path(pd, raw)
    plan_file = resolve_project_path(pd, raw, must_exist=True)
    plan = read_json(plan_file)
    if not isinstance(plan, dict):
        raise ProjectError(f"الخطة ليست JSON: {plan_file}")
    from .plan_time import plan_frame_rate

    rel = relative_project_path(pd, plan_file)
    man["storyboard"] = {
        "active": rel,
        "sha256": sha256_file(plan_file),
        "format_version": "2.0" if plan.get("timebase") else "1.0",
    }
    man["fps"] = frame_rate_json(plan_frame_rate(plan))
    man["updated_at"] = utc_now()
    return write_manifest(pd, man)


def _existing_manifest_values(pd: Path) -> dict:
    try:
        return read_manifest(pd) or {}
    except ProjectError:
        return {}


def _load_json_optional(path: Path) -> Any:
    try:
        return read_json(path)
    except Exception:
        return None


def _has_abs_plan_paths(plan: dict) -> bool:
    for scene in plan.get("scenes", []) or []:
        if not isinstance(scene, dict):
            continue
        for value in scene.get("assets_used", []) or []:
            if isinstance(value, str) and Path(value).is_absolute():
                return True
        for el in scene.get("elements", []) or []:
            if not isinstance(el, dict):
                continue
            for key in ("asset", "texture"):
                value = el.get(key)
                if isinstance(value, str) and Path(value).is_absolute():
                    return True
    return False


def _asset_entries(pd: Path, assets_index: Path | None) -> list[dict]:
    if not assets_index or not assets_index.exists():
        return []
    data = _load_json_optional(assets_index)
    if not isinstance(data, list):
        return []
    out: list[dict] = []
    for rec in data:
        if not isinstance(rec, dict) or not rec.get("path"):
            continue
        try:
            rel = relative_project_path(pd, rec["path"])
        except ProjectError:
            continue
        path = pd / rel
        if not path.exists():
            continue
        decision = rec.get("decision") if isinstance(rec.get("decision"), dict) else {}
        out.append(
            {
                "path": rel,
                "sha256": rec.get("sha256") or sha256_file(path),
                "bytes": int(rec.get("bytes") or path.stat().st_size),
                "kind": rec.get("kind"),
                "mime": rec.get("mime"),
                "origin": {
                    "kind": rec.get("source") or "retrieved",
                    "url": rec.get("url"),
                    "page_url": rec.get("page_url"),
                    "retrieved_at": rec.get("retrieved_at"),
                    "title": rec.get("title"),
                    "author": rec.get("author"),
                },
                "license": {
                    "name": rec.get("license") or "UNKNOWN",
                    "url": rec.get("license_url") or "",
                    "attribution_required": bool(rec.get("attr") or decision.get("needs_attribution")),
                },
                "approved_by": None,
                "approved_at": None,
                "status": "retrieved",
            }
        )
    return out


def _render_entries(pd: Path) -> list[dict]:
    render_dir = pd / "render"
    if not render_dir.exists():
        return []
    out: list[dict] = []
    for path in sorted(render_dir.iterdir(), key=lambda p: p.name.lower()):
        if not path.is_file() or path.suffix.lower() not in (".mp4", ".mov", ".mkv", ".webm", ".wav"):
            continue
        st = path.stat()
        out.append(
            {
                "path": relative_project_path(pd, path),
                "role": "preview" if "preview" in path.stem.lower() else "deliverable",
                "sha256": sha256_file(path),
                "bytes": st.st_size,
                "created_at": datetime.fromtimestamp(st.st_mtime, timezone.utc)
                .replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z"),
                "status": "existing",
                "validation": None,
            }
        )
    return out


def infer_manifest(
    project_dir: str | Path,
    *,
    project_id: str | None = None,
    active_plan: str | Path | None = None,
    title: str | None = None,
    language: str | None = None,
    now: str | None = None,
) -> dict:
    """Build a manifest from an existing project without moving or editing files."""
    pd = _project_root(project_dir)
    old = _existing_manifest_values(pd)
    pid = str(project_id or old.get("project_id") or pd.name)
    if not SAFE_ID.fullmatch(pid):
        raise ProjectError(f"معرّف مشروع غير صالح: {pid!r}")

    script_graph_path = pd / "script" / "scriptgraph.json"
    script_text_path = pd / "script" / "script.txt"
    research_path = pd / "research" / "research.json"
    assets_index_path = pd / "research" / "assets.json"
    graph = _load_json_optional(script_graph_path) or {}
    research = _load_json_optional(research_path) or {}

    if active_plan is not None:
        if Path(active_plan).is_absolute():
            active_plan = relative_project_path(pd, active_plan)
        plan_path = resolve_project_path(pd, active_plan, must_exist=True)
    else:
        preferred = pd / "storyboard" / "plan_v2.json"
        plan_path = preferred if preferred.exists() else pd / "storyboard" / "plan.json"
        plan_path = resolve_project_path(
            pd, relative_project_path(pd, plan_path), must_exist=True
        )

    plan = _load_json_optional(plan_path)
    if not isinstance(plan, dict):
        raise ProjectError(f"الخطة النشطة غير صالحة: {plan_path}")
    try:
        rate = coerce_frame_rate(plan.get("fps", 24))
    except TimebaseError as exc:
        raise ProjectError(f"معدل إطارات الخطة غير صالح: {exc}") from exc

    lang = str(language or old.get("language") or plan.get("lang") or graph.get("lang") or "ar")
    canvas = plan.get("canvas") or old.get("canvas") or [2560, 1440]
    narration = None
    try:
        from ..audio.narration import load_narration

        narration = load_narration(pd)
    except Exception:
        narration = None
    alignment_path = pd / "audio" / "alignment.json"
    assets = _asset_entries(pd, assets_index_path if assets_index_path.exists() else None)
    renders = _render_entries(pd)

    audio: dict[str, Any] = {
        "narration": None,
        "alignment": relative_project_path(pd, alignment_path) if alignment_path.exists() else None,
    }
    if narration and narration.get("path"):
        try:
            nar_rel = relative_project_path(pd, narration["path"])
        except ProjectError:
            nar_rel = None
        if nar_rel:
            audio.update(
                {
                    "narration": nar_rel,
                    "sha256": narration.get("sha256"),
                    "codec": narration.get("codec"),
                    "sample_rate": narration.get("sample_rate"),
                    "channels": narration.get("channels"),
                    "total_samples": narration.get("total_samples"),
                    "duration_exact": narration.get("duration_exact"),
                    "duration_sec": narration.get("duration_sec"),
                }
            )
    if alignment_path.exists():
        audio["alignment_sha256"] = sha256_file(alignment_path)

    unresolved: list[dict] = []
    if not audio.get("narration"):
        unresolved.append(
            {
                "id": "narration-missing",
                "kind": "audio",
                "blocking": False,
                "message": "لا يوجد تعليق صوتي معتمد؛ مدة الخطة تقديرية وليست مزامنة صوت.",
            }
        )
    pending_assets = [a for a in assets if not a.get("approved_by") or not a.get("approved_at")]
    if pending_assets:
        unresolved.append(
            {
                "id": "assets-pending-approval",
                "kind": "assets",
                "blocking": True,
                "message": f"{len(pending_assets)} أصلًا مسترجعًا ينتظر موافقة بشرية قبل الإنتاج.",
            }
        )
    if _has_abs_plan_paths(plan):
        unresolved.append(
            {
                "id": "absolute-plan-paths",
                "kind": "paths",
                "blocking": False,
                "message": "الخطة النشطة تحمل بعض المسارات المطلقة القديمة؛ لم تُعدّل أثناء الترحيل.",
            }
        )
    if not isinstance(plan.get("fps"), dict):
        unresolved.append(
            {
                "id": "legacy-numeric-fps",
                "kind": "timebase",
                "blocking": False,
                "message": "الخطة النشطة تحمل fps رقميًا قديمًا؛ يُطبّع في الذاكرة إلى كسر عقلاني.",
            }
        )

    created = old.get("created_at") or now or utc_now()
    updated = now or utc_now()
    status = old.get("status") if old.get("status") in STATUSES else ("planned" if plan_path.exists() else "draft")

    return {
        "schema_version": SCHEMA_VERSION,
        "project_id": pid,
        "title": str(title or old.get("title") or pid),
        "language": lang,
        "canvas": [int(canvas[0]), int(canvas[1])],
        "fps": frame_rate_json(rate),
        "status": status,
        "created_at": created,
        "updated_at": updated,
        "paths": {
            "script": relative_project_path(pd, script_graph_path) if script_graph_path.exists() else None,
            "script_text": relative_project_path(pd, script_text_path) if script_text_path.exists() else None,
            "research": relative_project_path(pd, research_path) if research_path.exists() else None,
            "assets_index": relative_project_path(pd, assets_index_path) if assets_index_path.exists() else None,
        },
        "storyboard": {
            "active": relative_project_path(pd, plan_path),
            "sha256": sha256_file(plan_path),
            "format_version": "2.0" if plan.get("timebase") else "1.0",
        },
        "audio": audio,
        "asset_policy": {
            "generated_is_evidence": False,
            "retrieved_requires_approval": True,
            "requires_origin": True,
            "requires_license": True,
        },
        "assets": assets,
        "unresolved": unresolved,
        "renders": renders,
        "render": {
            "fps_source": "plan",
            "width": int(canvas[0]),
            "height": int(canvas[1]),
            "default_out_size": [1280, 720],
            "video_codec": "h264",
            "audio_codec": "aac",
        },
        "studio": {
            "kind": "rasm-pro",
            "project_id": pid,
        },
    }


def _require_rel(pd: Path, value: Any, label: str, errors: list[str], *, must_exist: bool = True) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{label}: مطلوب مسار نسبي")
        return None
    try:
        return resolve_project_path(pd, value, must_exist=must_exist)
    except ProjectError as exc:
        errors.append(f"{label}: {exc}")
        return None


def _hash_check(path: Path, expected: Any, label: str, errors: list[str]) -> None:
    if not expected:
        errors.append(f"{label}: الهاش مطلوب")
        return
    actual = sha256_file(path)
    if str(expected).lower() != actual.lower():
        errors.append(f"{label}: الهاش لا يطابق ({actual} != {expected})")


def validate_manifest(
    manifest: dict,
    project_dir: str | Path,
    *,
    check_assets: bool = True,
    check_renders: bool = True,
    check_plan: bool = True,
) -> dict:
    """Validate the manifest and every file/hash it declares."""
    pd = Path(project_dir).resolve()
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(manifest, dict):
        return {
            "ok": False,
            "errors": ["المانيفست ليس كائنًا JSON"],
            "warnings": [],
            "stats": {"assets": 0, "renders": 0, "unresolved": 0},
        }

    if manifest.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version يجب أن يكون {SCHEMA_VERSION!r}")
    pid = manifest.get("project_id")
    if not isinstance(pid, str) or not SAFE_ID.fullmatch(pid):
        errors.append("project_id غير صالح")
    elif pid != pd.name:
        warnings.append(f"project_id ({pid}) لا يطابق اسم المجلد ({pd.name})")
    if manifest.get("status") not in STATUSES:
        errors.append(f"status يجب أن يكون أحد {STATUSES}")
    if not isinstance(manifest.get("language"), str) or not manifest.get("language"):
        errors.append("language مطلوب")
    if not isinstance(manifest.get("title"), str) or not manifest.get("title").strip():
        errors.append("title مطلوب")
    for key in ("created_at", "updated_at"):
        if not isinstance(manifest.get(key), str) or not manifest.get(key):
            errors.append(f"{key} مطلوب")

    canvas = manifest.get("canvas")
    if (
        not isinstance(canvas, list)
        or len(canvas) != 2
        or not all(isinstance(v, int) and not isinstance(v, bool) and v > 0 for v in canvas)
    ):
        errors.append("canvas يجب أن يكون [عرض, ارتفاع] بأعداد صحيحة موجبة")

    try:
        man_rate = coerce_frame_rate(manifest.get("fps"))
    except TimebaseError as exc:
        errors.append(f"fps غير صالح: {exc}")
        man_rate = None

    paths = manifest.get("paths")
    if not isinstance(paths, dict):
        errors.append("paths يجب أن يكون كائنًا")
        paths = {}
    script_path = _require_rel(pd, paths.get("script"), "paths.script", errors, must_exist=False) if paths.get("script") else None
    if paths.get("script") and script_path and not script_path.exists():
        errors.append(f"paths.script غير موجود: {paths.get('script')}")
    research_path = _require_rel(pd, paths.get("research"), "paths.research", errors, must_exist=False) if paths.get("research") else None
    if paths.get("research") and research_path and not research_path.exists():
        errors.append(f"paths.research غير موجود: {paths.get('research')}")
    if not paths.get("script"):
        warnings.append("paths.script غير معلن")
    if not paths.get("research"):
        warnings.append("paths.research غير معلن")

    storyboard = manifest.get("storyboard")
    if not isinstance(storyboard, dict):
        errors.append("storyboard يجب أن يكون كائنًا")
        storyboard = {}
    plan_path = _require_rel(pd, storyboard.get("active"), "storyboard.active", errors)
    plan_data: dict | None = None
    if plan_path and plan_path.exists():
        _hash_check(plan_path, storyboard.get("sha256"), "storyboard.sha256", errors)
        plan_data = _load_json_optional(plan_path)
        if not isinstance(plan_data, dict):
            errors.append("storyboard.active ليس خطة JSON صالحة")
        elif man_rate is not None:
            try:
                plan_rate = coerce_frame_rate(plan_data.get("fps", 24))
            except TimebaseError as exc:
                errors.append(f"fps الخطة النشطة غير صالح: {exc}")
            else:
                if plan_rate.value != man_rate.value:
                    errors.append(
                        f"fps المانيفست ({man_rate}) لا يطابق الخطة النشطة ({plan_rate})"
                    )
            if check_plan:
                try:
                    from ..stages.validate_plan import validate_plan

                    report = validate_plan(plan_data, project_dir=pd, check_assets=check_assets)
                except Exception as exc:  # defensive: a broken plan is not a warning
                    errors.append(f"تعذّر تشغيل مدقق الخطة: {exc}")
                else:
                    if not report.get("ok"):
                        errors.extend(f"الخطة النشطة: {e}" for e in report.get("errors", []))
                    warnings.extend(f"الخطة النشطة: {w}" for w in report.get("warnings", []))

    audio = manifest.get("audio")
    if not isinstance(audio, dict):
        warnings.append("audio غير معلن")
        audio = {}
    nar_path = None
    if audio.get("narration"):
        nar_path = _require_rel(pd, audio.get("narration"), "audio.narration", errors)
        if nar_path:
            _hash_check(nar_path, audio.get("sha256"), "audio.sha256", errors)
    if audio.get("alignment"):
        al_path = _require_rel(pd, audio.get("alignment"), "audio.alignment", errors)
        if al_path:
            _hash_check(al_path, audio.get("alignment_sha256"), "audio.alignment_sha256", errors)

    assets = manifest.get("assets") or []
    if not isinstance(assets, list):
        errors.append("assets يجب أن يكون قائمة")
        assets = []
    if check_assets:
        for i, asset in enumerate(assets, 1):
            where = f"assets[{i}]"
            if not isinstance(asset, dict):
                errors.append(f"{where}: يجب أن يكون كائنًا")
                continue
            ap = _require_rel(pd, asset.get("path"), f"{where}.path", errors)
            if ap:
                _hash_check(ap, asset.get("sha256"), f"{where}.sha256", errors)
            origin = asset.get("origin")
            if not isinstance(origin, dict) or not (origin.get("kind") or origin.get("url")):
                errors.append(f"{where}.origin مطلوب")
            license_ = asset.get("license")
            if not isinstance(license_, dict) or not license_.get("name"):
                errors.append(f"{where}.license.name مطلوب")
            if asset.get("approved_by") and not asset.get("approved_at"):
                errors.append(f"{where}: approved_by بلا approved_at")
            if asset.get("approved_at") and not asset.get("approved_by"):
                errors.append(f"{where}: approved_at بلا approved_by")

    renders = manifest.get("renders") or []
    if not isinstance(renders, list):
        errors.append("renders يجب أن يكون قائمة")
        renders = []
    if check_renders:
        for i, render in enumerate(renders, 1):
            where = f"renders[{i}]"
            if not isinstance(render, dict):
                errors.append(f"{where}: يجب أن يكون كائنًا")
                continue
            rp = _require_rel(pd, render.get("path"), f"{where}.path", errors)
            if rp:
                _hash_check(rp, render.get("sha256"), f"{where}.sha256", errors)

    unresolved = manifest.get("unresolved") or []
    if not isinstance(unresolved, list):
        errors.append("unresolved يجب أن يكون قائمة")
        unresolved = []
    for i, item in enumerate(unresolved, 1):
        if not isinstance(item, dict) or not item.get("message"):
            errors.append(f"unresolved[{i}]: يجب أن يحمل message")
        elif not isinstance(item.get("blocking"), bool):
            errors.append(f"unresolved[{i}].blocking يجب أن يكون boolean")

    if not isinstance(manifest.get("asset_policy"), dict):
        errors.append("asset_policy مطلوب")
    if not isinstance(manifest.get("render"), dict):
        errors.append("render مطلوب")
    if not isinstance(manifest.get("studio"), dict):
        errors.append("studio مطلوب")

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "stats": {
            "assets": len(assets),
            "renders": len(renders),
            "unresolved": len(unresolved),
            "pending_assets": sum(
                1 for a in assets if isinstance(a, dict) and (not a.get("approved_by") or not a.get("approved_at"))
            ),
        },
    }
