"""أدلة بصرية لكل حلقة: آخر إطار من كل مشهد + ورقة تواصل.

    .venv\\Scripts\\python.exe tools\\extract_episode_frames.py episode-01-ar

يكتب ``projects/<id>/render/frames/scene-NN-end.png`` لكل مشهد (آخر إطار
فيه: بعد أن يكتمل الرسم) وورقة تواصل ``contact-sheet-end.png`` للمراجعة بالعين.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.core.paths import PROJECTS  # noqa: E402
from engine.core.util import read_json  # noqa: E402


def _ffmpeg() -> str:
    from engine.render.video import require_ffmpeg

    return require_ffmpeg()


def _active_plan(project_dir: Path) -> Path | None:
    manifest = project_dir / "project.json"
    if manifest.exists():
        data = read_json(manifest) or {}
        active = str((data.get("storyboard") or {}).get("active") or "")
        if active:
            candidate = project_dir / active
            if candidate.exists():
                return candidate
    plans = sorted(
        (project_dir / "storyboard").glob("plan*.json"),
        key=lambda p: p.stat().st_mtime,
    )
    return plans[-1] if plans else None


def main() -> int:
    ap = argparse.ArgumentParser(description="evidence frames for an episode")
    ap.add_argument("project")
    ap.add_argument("--out", default=None)
    ap.add_argument("--tile", default="640x360")
    args = ap.parse_args()

    from PIL import Image, ImageDraw

    project_dir = PROJECTS / args.project
    video = Path(args.out) if args.out else project_dir / "render" / "episode.mp4"
    if not video.exists():
        print(f"no video: {video}", file=sys.stderr)
        return 2
    plan_path = _active_plan(project_dir)
    if plan_path is None:
        print(f"no plan for {args.project}", file=sys.stderr)
        return 2
    plan = read_json(plan_path)
    frames = project_dir / "render" / "frames"
    frames.mkdir(parents=True, exist_ok=True)
    exe = _ffmpeg()
    for scene in plan.get("scenes") or []:
        index = int(scene["end_frame"]) - 1
        out = frames / f"scene-{int(scene['id']):02d}-end.png"
        subprocess.run(
            [
                exe, "-y", "-v", "error", "-i", str(video),
                "-vf", f"select=eq(n\\,{index})", "-fps_mode", "passthrough",
                "-frames:v", "1", str(out),
            ],
            check=True,
        )
    width, height = (int(v) for v in args.tile.lower().split("x"))
    scenes = plan.get("scenes") or []
    cols = 3
    rows = (len(scenes) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * width, rows * height), (255, 255, 255))
    for position, scene in enumerate(scenes):
        path = frames / f"scene-{int(scene['id']):02d}-end.png"
        if not path.exists():
            continue
        image = Image.open(path).convert("RGB").resize((width, height), Image.LANCZOS)
        sheet.paste(image, ((position % cols) * width, (position // cols) * height))
    sheet_path = frames / "contact-sheet-end.png"
    sheet.save(sheet_path)
    print(f"plan: {plan_path}")
    print(f"frames: {len(scenes)} → {frames}")
    print(f"contact sheet: {sheet_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
