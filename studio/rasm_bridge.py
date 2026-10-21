"""Bridge between Studio and rasm-pro production engine."""
from __future__ import annotations

import json
import sys
from pathlib import Path

RASM_ROOT = Path(__file__).resolve().parent.parent / "rasm-pro"
if str(RASM_ROOT) not in sys.path:
    sys.path.insert(0, str(RASM_ROOT))

RASM_AVAILABLE = False
_RASM_ERROR = ""
try:
    from engine.core import paths as rasm_paths  # noqa: E402
    from engine.audio import (  # noqa: E402
        import_narration as rasm_import_narration,
        load_narration as rasm_load_narration,
        probe_audio as rasm_probe_audio,
        baseline_align as rasm_baseline_align,
        save_alignment as rasm_save_alignment,
        load_alignment as rasm_load_alignment,
        alignment_frames as rasm_alignment_frames,
    )
    from engine.stages import understanding as rasm_understanding  # noqa: E402
    from engine.stages import research as rasm_research  # noqa: E402
    from engine.stages import plan as rasm_plan  # noqa: E402
    from engine.stages.validate_plan import validate_plan as rasm_validate_plan  # noqa: E402
    from engine.core.timebase import FrameRate, SampleRate, coerce_frame_rate  # noqa: E402
    from engine.core import project as rasm_project  # noqa: E402
    from engine.core import assets as rasm_assets  # noqa: E402
    from engine.render import Director  # noqa: E402
    from engine.render.validate import validate_video as rasm_validate_video  # noqa: E402
    from engine.core.util import read_json as rasm_read_json  # noqa: E402
    RASM_AVAILABLE = True
except Exception as e:
    _RASM_ERROR = str(e)


def _require():
    if not RASM_AVAILABLE:
        raise RuntimeError("rasm-pro unavailable: " + _RASM_ERROR)


def rasm_project_dir(project_id):
    _require()
    return rasm_paths.project_dir(project_id)


def understand_script(script, project_id, offline=True):
    _require()
    graph = rasm_understanding.analyze_script(script, force_offline=offline)
    pd = rasm_paths.project_dir(project_id)
    out = rasm_understanding.save_graph(graph, pd)
    (pd / "script" / "script.txt").write_text(script, encoding="utf-8")
    return {"graph": graph, "saved": str(out), "project_dir": str(pd)}


def research_project(project_id, max_entities=14, download=False):
    _require()
    pd = rasm_paths.project_dir(project_id)
    graph = json.loads((pd / "script" / "scriptgraph.json").read_text(encoding="utf-8"))
    return rasm_research.research_script(graph, pd, max_entities=max_entities, download=download)


def import_narration_studio(project_id, src_path, copy=True, deep=True, note=""):
    _require()
    pd = rasm_paths.project_dir(project_id)
    man = rasm_import_narration(pd, src_path, copy=copy, deep=deep, note=note)
    try:
        graph_path = pd / "script" / "scriptgraph.json"
        if graph_path.exists() and man.get("total_samples") and man.get("sample_rate"):
            graph = json.loads(graph_path.read_text(encoding="utf-8"))
            al = rasm_baseline_align(graph.get("scenes", []), int(man["total_samples"]), int(man["sample_rate"]))
            rasm_save_alignment(al, pd)
            man["alignment_level"] = al.level
            man["alignment_segments"] = len(al.segments)
    except Exception as e:
        man["alignment_error"] = str(e)
    return man


def load_narration_studio(project_id):
    if not RASM_AVAILABLE:
        return None
    pd = rasm_paths.project_dir(project_id)
    return rasm_load_narration(pd)


def project_manifest_studio(project_id):
    if not RASM_AVAILABLE:
        return None
    pd = rasm_paths.project_dir(project_id)
    return rasm_project.read_manifest(pd)


def load_active_plan_studio(project_id):
    _require()
    pd = rasm_paths.project_dir(project_id)
    man = rasm_project.read_manifest(pd)
    if man is not None:
        plan, path = rasm_project.load_active_plan(pd, man)
        return plan, path, man
    for name in ("plan_v2.json", "plan.json"):
        path = pd / "storyboard" / name
        if path.exists():
            return rasm_read_json(path), path, None
    raise RuntimeError("no plan; run build_plan first")


def build_plan_studio(project_id, max_scenes=None, fps=None):
    _require()
    pd = rasm_paths.project_dir(project_id)
    graph = json.loads((pd / "script" / "scriptgraph.json").read_text(encoding="utf-8"))
    research = {}
    rp = pd / "research" / "research.json"
    if rp.exists():
        research = json.loads(rp.read_text(encoding="utf-8"))
    rate = coerce_frame_rate(fps) if fps is not None else None
    man = rasm_project.read_manifest(pd)
    if rate is None and man and man.get("fps") is not None:
        rate = coerce_frame_rate(man["fps"])
    plan = rasm_plan.build_plan(
        graph, research, project_dir=pd, max_scenes=max_scenes, fps=rate
    )
    report = rasm_validate_plan(plan, project_dir=pd)
    if not report.get("ok"):
        detail = "; ".join(report.get("errors", [])[:5])
        raise RuntimeError(f"built plan is invalid; not saved: {detail}")
    out = rasm_plan.save_plan(plan, pd)
    if man is not None:
        rasm_project.activate_plan(pd, out)
    return plan


def rasm_to_studio_project(plan, project_id):
    scenes = []
    for s in plan.get("scenes", []):
        narration = s.get("narration") or ""
        words = narration.split()[:7]
        title = " ".join(words) if words else str(s.get("id", ""))
        scenes.append({
            "text": narration,
            "title": title,
            "duration": float(s.get("duration", 6.0)),
            "assets": [],
            "layout": "focus",
            # Lossless rasm fields: Studio may ignore them, but a round-trip
            # must never silently drop elements or selected assets.
            "rasm_id": s.get("id"),
            "rasm_elements": s.get("elements", []),
            "rasm_assets_used": s.get("assets_used", []),
            "rasm_start_frame": s.get("start_frame"),
            "rasm_end_frame": s.get("end_frame"),
            "rasm_duration_frames": s.get("duration_frames"),
            "rasm_start_sample": s.get("start_sample"),
            "rasm_end_sample": s.get("end_sample"),
        })
    proj = {
        "version": 1,
        "id": project_id,
        "title": "Rasm plan",
        "script": "",
        "domain": "life",
        "duration": float(plan.get("stats", {}).get("estimated_duration", 0) or 0),
        "planner": "rasm",
        "resolution": "1080p",
        "accent": "#149e91",
        "renderer": "whiteboard",
        "hand": True,
        "camera": True,
        "paper": "cream",
        "scenes": scenes,
        "rasm_timing": plan.get("timing", {}),
        "rasm_audio": plan.get("audio", {}),
        "rasm_fps": plan.get("fps"),
        "rasm_timebase": plan.get("timebase", {}),
        "rasm_plan": plan,
    }
    return proj


def asset_approvals_studio(project_id):
    """Approval state of every project asset (Studio never implies approval)."""
    if not RASM_AVAILABLE:
        return None
    pd = rasm_paths.project_dir(project_id)
    man = rasm_project.read_manifest(pd)
    if man is None:
        return {"assets": [], "counts": {}, "gate": None}
    plan = None
    try:
        plan, _path, _man = load_active_plan_studio(project_id)
    except Exception:
        plan = None
    try:
        projected = rasm_assets.sync_manifest_approvals(man, pd)
    except Exception:
        projected = man
    counts = {}
    rows = []
    for asset in projected.get("assets") or []:
        if not isinstance(asset, dict):
            continue
        approval = asset.get("approval") or {}
        state = str(approval.get("decision") or "pending")
        counts[state] = counts.get(state, 0) + 1
        rows.append(
            {
                "asset_id": asset.get("asset_id"),
                "path": asset.get("path"),
                "decision": state,
                "reviewer": approval.get("reviewer") or "",
                "reviewed_at": approval.get("reviewed_at") or "",
                "license": (asset.get("license") or {}).get("name"),
                "origin": (asset.get("origin") or {}).get("kind"),
            }
        )
    gate = None
    if plan is not None:
        try:
            report = rasm_assets.evaluate_gate(plan, pd, manifest=projected, mode="final")
            gate = {
                "ok": report.ok,
                "blocking": [
                    {"reason": b["reason"], "path": b["path"], "detail": b["detail"]}
                    for b in report.blocking
                ],
                "used": len(report.used),
            }
        except Exception as exc:
            gate = {"ok": False, "blocking": [{"reason": "gate-error", "detail": str(exc)}], "used": 0}
    return {"assets": rows, "counts": counts, "gate": gate}


def render_project_studio(
    project_id,
    out_path=None,
    fps=None,
    size=(1280, 720),
    max_seconds=None,
    audio=None,
    mode="preview",
):
    """Render through Studio.

    Studio renders are interactive previews by default (``mode='preview'``):
    unapproved assets are allowed but reported.  A production render must pass
    ``mode='final'`` and is refused while assets are unapproved.
    """
    _require()
    pd = rasm_paths.project_dir(project_id)
    plan, plan_path, man = load_active_plan_studio(project_id)
    if man is not None:
        report = rasm_assets.evaluate_gate(plan, pd, manifest=man, mode=mode)
        if not report.ok:
            detail = "; ".join(f"{b['reason']}: {b['path'] or b['display']}" for b in report.blocking[:5])
            raise RuntimeError(f"asset gate closed ({mode}): {detail}")
        for item in report.warnings[:5]:
            print(f"warning: {item['reason']}: {item['path']} - {item['detail']}")
        # the narration gate is the same contract as the CLI's
        from engine.audio.gate import evaluate_narration_gate
        from engine.audio.loudness import TARGETS

        audio_gate = evaluate_narration_gate(
            pd, plan, mode=mode, target_lufs=TARGETS.get("video")
        )
        if not audio_gate.ok:
            detail = "; ".join(f"{b['reason']}: {b['detail']}" for b in audio_gate.blocking[:5])
            raise RuntimeError(f"narration gate closed ({mode}): {detail}")
        for item in audio_gate.warnings[:5]:
            print(f"warning: {item['reason']}: {item['detail']}")
    audio_file = audio
    if audio_file is None:
        plan_audio = plan.get("audio") or {}
        candidate = plan_audio.get("file")
        if candidate:
            candidate = Path(candidate)
            if not candidate.is_absolute():
                candidate = pd / candidate
            if candidate.exists():
                audio_file = candidate
        if audio_file is None:
            nar = rasm_load_narration(pd)
            if nar:
                audio_file = nar.get("path")
    canvas = tuple(plan.get("canvas") or [2560, 1440])
    director = Director(
        plan, canvas=canvas, out_size=size, fps=fps, crf=19, project_dir=pd
    )
    out = Path(out_path) if out_path else (pd / "render" / "preview.mp4")
    out.parent.mkdir(parents=True, exist_ok=True)
    result = director.render(out, audio=audio_file, max_seconds=max_seconds)
    result["plan_path"] = str(plan_path)
    result["manifest"] = str(rasm_project.project_manifest_path(pd)) if man is not None else None
    result["audio"] = str(audio_file) if audio_file else None
    result["mode"] = mode
    return result


def validate_studio_render(result, size, expect_audio=False):
    _require()
    return rasm_validate_video(
        result["out"],
        expect_size=size,
        expect_fps=result.get("fps"),
        expect_frames=result.get("frames"),
        expect_audio=expect_audio,
        expect_duration_sec=result.get("duration_sec_exact"),
        tolerance_frames=1,
    )
