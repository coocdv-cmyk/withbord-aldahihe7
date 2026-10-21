"""Render the visual corpus of the template families.

For every family and every scene role we render one finished still and lay
the tiles out in a contact sheet, so the owner can *see* the three families
instead of reading their names.

    python tools/render_family_corpus.py --out qa/stage6

Two sheets are produced (Arabic and English).  The renders are real: the same
Director, the same plan builder, the same fonts and the same assets.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.render import Director  # noqa: E402
from engine.stages.families import FAMILIES, SCENE_ROLES  # noqa: E402
from engine.stages.plan import build_plan  # noqa: E402

CANVAS = (2560, 1440)
OUT_SIZE = (640, 360)

SAMPLES = {
    "ar": {
        "lang": "ar",
        "hook": "الحرب العالمية الأولى",
        "scenes": [
            {"id": 1, "narration": "في صيف 1914 اشتعلت الحرب العالمية الأولى.", "duration": 12.0, "needs": []},
            {"id": 2, "narration": "معركة السوم 1916: خنادق ومدافعون وفرسان.", "duration": 12.0, "needs": []},
            {"id": 3, "narration": "دخلت الولايات المتحدة الحرب في 1917.", "duration": 12.0, "needs": []},
            {"id": 4, "narration": "معاهدة فرساي 1919 رسمت خريطة العالم الحديث.", "duration": 12.0, "needs": []},
        ],
    },
    "en": {
        "lang": "en",
        "hook": "The First World War",
        "scenes": [
            {"id": 1, "narration": "In the summer of 1914 the world went to war.", "duration": 12.0, "needs": []},
            {"id": 2, "narration": "The Somme in 1916: trenches, gunners and horses.", "duration": 12.0, "needs": []},
            {"id": 3, "narration": "The United States entered the war in 1917.", "duration": 12.0, "needs": []},
            {"id": 4, "narration": "The Treaty of Versailles redrew the modern map.", "duration": 12.0, "needs": []},
        ],
    },
}


def _ffmpeg() -> str:
    from engine.render.video import require_ffmpeg

    return require_ffmpeg()


def render_still(plan: dict, index: int, tmp: Path) -> Image.Image:
    """Render one scene of a plan and return its last frame."""
    scene = dict(plan["scenes"][index])
    frames = int(scene.get("duration_frames") or 0) or int(round(float(scene.get("duration") or 6.0) * 24))
    scene["start_frame"] = 0
    scene["end_frame"] = frames
    scene["duration_frames"] = frames
    scene.pop("start_sample", None)
    scene.pop("end_sample", None)
    scene_plan = dict(plan)
    scene_plan["scenes"] = [scene]
    scene_plan["stats"] = dict(plan.get("stats") or {})
    scene_plan.pop("timebase", None)
    video = tmp / f"scene{index}.mp4"
    director = Director(scene_plan, canvas=CANVAS, out_size=OUT_SIZE, fps=24)
    res = director.render(video)
    last = tmp / f"scene{index}.png"
    subprocess.run(
        [
            _ffmpeg(),
            "-y",
            "-v",
            "error",
            "-sseof",
            "-0.2",
            "-i",
            str(video),
            "-frames:v",
            "1",
            str(last),
        ],
        capture_output=True,
        check=True,
    )
    return Image.open(last).convert("RGB")


def build_sheet(lang: str, out_path: Path) -> Path:
    sample = SAMPLES[lang]
    graph = {
        "lang": sample["lang"],
        "hook": sample["hook"],
        "source_hash": f"corpus-{lang}",
        "scenes": sample["scenes"],
    }
    tiles = []
    with tempfile.TemporaryDirectory(prefix="rasm-corpus-") as td:
        tmp = Path(td)
        for family_name in FAMILIES:
            plan = build_plan(graph, {}, project_dir=tmp, fps=24, family=family_name)
            for index, role in enumerate(SCENE_ROLES):
                texts = [
                    (e.get("text") or "").replace("\n", " ")
                    for e in plan["scenes"][index]["elements"]
                    if e.get("type") == "text"
                ]
                print(f"  tile {family_name}/{role}: {texts}")
                still = render_still(plan, index, tmp)
                tiles.append((family_name, role, still))

    cols = len(FAMILIES)
    rows = len(SCENE_ROLES)
    pad = 12
    label_h = 22
    w, h = tiles[0][2].size
    sheet = Image.new(
        "RGB",
        (cols * w + pad * (cols + 1), rows * (h + label_h) + pad * (rows + 1)),
        (245, 243, 238),
    )
    draw = ImageDraw.Draw(sheet)
    for i, (family_name, role, still) in enumerate(tiles):
        col, row = i % cols, i // cols
        x = pad + col * (w + pad)
        y = pad + row * (h + label_h + pad)
        sheet.paste(still, (x, y))
        draw.text((x + 2, y + h + 4), f"{family_name} · {role}", fill=(40, 38, 34))
    sheet.save(out_path)
    return out_path


def main() -> int:
    ap = argparse.ArgumentParser(description="render the family visual corpus")
    ap.add_argument("--out", default=str(ROOT / "qa" / "stage6"))
    args = ap.parse_args()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    for lang in ("ar", "en"):
        path = build_sheet(lang, out_dir / f"family-corpus-{lang}.png")
        print(f"✔ {path} ({path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
