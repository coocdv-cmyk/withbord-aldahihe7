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
    from engine.core.timebase import FrameRate, SampleRate  # noqa: E402
    from engine.render import Director  # noqa: E402
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


def build_plan_studio(project_id, max_scenes=None):
    _require()
    pd = rasm_paths.project_dir(project_id)
    graph = json.loads((pd / "script" / "scriptgraph.json").read_text(encoding="utf-8"))
    research = {}
    rp = pd / "research" / "research.json"
    if rp.exists():
        research = json.loads(rp.read_text(encoding="utf-8"))
    plan = rasm_plan.build_plan(graph, research, project_dir=pd, max_scenes=max_scenes)
    rasm_plan.save_plan(plan, pd)
    return plan


def rasm_to_studio_project(plan, project_id):
    scenes = []
    for s in plan.get("scenes", []):
        narration = s.get("narration", "")
        words = narration.split()[:7]
        title = " ".join(words) if words else str(s.get("id", ""))
        scenes.append({
            "text": narration,
            "title": title,
            "duration": float(s.get("duration", 6.0)),
            "assets": [],
            "layout": "focus",
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
    }
    return proj


def render_project_studio(project_id, out_path=None, fps=24, size=(1280, 720), max_seconds=None, audio=None):
    _require()
    pd = rasm_paths.project_dir(project_id)
    plan = rasm_read_json(pd / "storyboard" / "plan.json")
    if not plan:
        raise RuntimeError("no plan; run build_plan first")
    audio_file = audio
    if audio_file is None:
        nar = rasm_load_narration(pd)
        if nar:
            audio_file = nar.get("path")
    canvas = tuple(plan.get("canvas") or [2560, 1440])
    director = Director(plan, canvas=canvas, out_size=size, fps=fps, crf=19)
    out = Path(out_path) if out_path else (pd / "render" / "preview.mp4")
    out.parent.mkdir(parents=True, exist_ok=True)
    return director.render(out, audio=audio_file, max_seconds=max_seconds)
