# -*- coding: utf-8 -*-
"""يجمع مخرجات ffprobe لكل مخرجات Phase 3.1 في ملف واحد (qa/phase31_ffprobe.txt)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from engine.audio.probe import require_ffprobe  # noqa: E402

FILES = [
    ("v2 improved film (Phase 3.1 deliverable)", ROOT / "projects" / "ww1" / "render" / "preview_v2.mp4"),
    ("v2 SFX track (real PD recordings, mixed)", ROOT / "projects" / "ww1" / "render" / "preview_v2.sfx.wav"),
    ("v1 plan replay (untouched plan.json re-rendered with the Phase 3.1 engine)", ROOT / "projects" / "ww1" / "render" / "preview_v1_plan_replay.mp4"),
    ("template clip: PREMIUM WHITEBOARD", ROOT / "qa" / "phase31_templates" / "premium_whiteboard.mp4"),
    ("template clip: DOCUMENTARY PAPER COLLAGE", ROOT / "qa" / "phase31_templates" / "documentary_collage.mp4"),
    ("template clip: TIMELINE / DATA STORY", ROOT / "qa" / "phase31_templates" / "timeline_data_story.mp4"),
    ("before/after diagnostic video", ROOT / "qa" / "phase31_diag" / "before_after.mp4"),
]

NOTES = [
    "",
    "## Recorded evidence — original v1 baseline (file overwritten, disclosed)",
    "  file: projects/ww1/render/preview.mp4  (measured 2026-10-19 11:0x, validated)",
    "  format: mov,mp4,m4a · duration=44.541667s · size=11434110 bytes · bit_rate=2053647",
    "  video: h264 1280x720 fps=24/1 frames=1069 pix=yuv420p dur=44.541667",
    "  audio: (none)",
    "  incident: overwritten at 14:31 by a render command that omitted --out (see",
    "  qa/phase31_repro/before/film_v1_stills/README.md). Original pixels preserved as stills in",
    "  qa/phase31_repro/before/film_v1_stills/, qa/phase31_repro/before/film/, and as the 'قبل' side",
    "  of the three film pairs in qa/phase31_diag/before_after.mp4.",
]


fp = require_ffprobe()
lines: list[str] = ["# Phase 3.1 — FFprobe evidence", "",
                    f"command: ffprobe -v error -show_streams -show_format -of json <file>", ""]
for title, path in FILES:
    lines.append(f"## {title}")
    lines.append(f"file: {path}")
    if not path.exists():
        lines.append("MISSING")
        lines.append("")
        continue
    r = subprocess.run([fp, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    try:
        d = json.loads(r.stdout)
    except Exception:
        lines.append(r.stdout or r.stderr)
        lines.append("")
        continue
    fmt = d.get("format", {})
    lines.append(f"format: {fmt.get('format_name')} · duration={fmt.get('duration')}s · size={fmt.get('size')} bytes · bit_rate={fmt.get('bit_rate')}")
    for s in d.get("streams", []):
        if s.get("codec_type") == "video":
            lines.append(
                f"  video: {s.get('codec_name')} {s.get('width')}x{s.get('height')} fps={s.get('r_frame_rate')} "
                f"frames={s.get('nb_frames')} pix={s.get('pix_fmt')} dur={s.get('duration')}"
            )
        elif s.get("codec_type") == "audio":
            lines.append(
                f"  audio: {s.get('codec_name')} {s.get('sample_rate')}Hz ch={s.get('channels')} "
                f"dur={s.get('duration')} bit_rate={s.get('bit_rate')}"
            )
    lines.append("")

out = ROOT / "qa" / "phase31_ffprobe.txt"
out.write_text("\n".join(lines), encoding="utf-8")
print("✔", out)
print("\n".join(lines[:40]))
