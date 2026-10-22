"""رندر **قابل للاستئناف**: كل مشهد جزءٌ مستقل، والحالة على القرص.

لماذا: رندر 25 دقيقة في طلقة واحدة يعني أن أي انهيار (أو قفلة كهرباء) يمحو
ساعة عمل.  الحل: نرندر كل مشهد إلى ملفه، ونحفظ ما أُنجز، ونعيد تشغيل ما بقي.

الآلية:

* ``render/parts/scene-NNN.mp4`` — جزء **صامت** لكل مشهد (بلا صوت: الصوت
  يُدمج مرة واحدة في النهاية، فلا accumulates أي انزياح).
* ``render/parts/state.json`` — ما أُنجز: بصمة الخطة، وحجم كل جزء، وإطاراته.
* ``concat`` بدمج المسارات (نسخ流的، بلا إعادة ترميز) ⇒ نفس عدد الإطارات بالضبط.
* عند إعادة التشغيل: نُكمل الأجزاء الناقصة فقط، والمُنجزة تُستعمل كما هي.

المقياس: الرندر الثاني بعد قطعٍ متعمّد يجب أن يكون أسرع، والنتيجة النهائية
لا تختلف عن الرندر المباشر: نفس الإطارات، ونفس فرق الصوت/الصورة.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

from ..core.log import get_logger
from ..core.util import sha256_file, write_json

log = get_logger("render.parts")

STATE_NAME = "state.json"


def parts_dir(out_path: str | Path) -> Path:
    return Path(out_path).parent / "parts"


def state_path(out_path: str | Path) -> Path:
    return parts_dir(out_path) / STATE_NAME


def load_state(out_path: str | Path) -> dict:
    p = state_path(out_path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(out_path: str | Path, state: dict) -> None:
    p = state_path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    write_json(p, state)


def _concat(parts: list[Path], out_path: Path, ffmpeg: str) -> None:
    """يدمج الأجزاء بنسخ التيار (بلا إعادة ترميز ⇒ الإطارات كما هي)."""
    list_file = out_path.parent / "parts" / "concat.txt"
    list_file.write_text(
        "\n".join(f"file '{p.as_posix()}'" for p in parts) + "\n", encoding="utf-8"
    )
    cmd = [
        ffmpeg, "-y", "-v", "error",
        "-f", "concat", "-safe", "0", "-i", str(list_file),
        "-c", "copy", "-movflags", "+faststart", str(out_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"concat failed: {proc.stderr[-300:]}")


def _merge_events(
    parts: list[tuple[Path, int]],
    out_path: Path,
) -> int:
    """يجمع أحداث القلم من الأجزاء ويصحّح زمنها النسبي لل فيلم المُدمج.

    كل جزء يُرسم وحده، فأحداثه بتوقيته هو (0 = أول إطار في الجزء).  في
    الفيديو المُدمج يجب أن يتحوّل الزمن إلى زمن الفيلم: لذلك نضيف إزاحة
    كل جزء (إطاراته السابقة).
    """
    events: list[dict] = []
    frame_offset = 0
    time_offset = 0.0
    for part, frames in parts:
        sfx_json = part.with_suffix(".sfx.json")
        if sfx_json.exists():
            try:
                data = json.loads(sfx_json.read_text(encoding="utf-8"))
            except Exception:
                data = {}
            for event in data.get("events") or []:
                item = dict(event)
                item["output_t"] = round(float(item.get("output_t") or 0.0) + time_offset, 6)
                item["output_frame"] = int(item.get("output_frame") or 0) + frame_offset
                events.append(item)
        frame_offset += int(frames)
        time_offset += int(frames) / 24.0
    if events:
        write_json(out_path.with_suffix(".sfx.json"), {"events": events, "frames": frame_offset})
    return len(events)


def render_resumable(
    director: Any,
    out_path: str | Path,
    *,
    plan_fingerprint: str,
    scene_bounds: list[dict],
    ffmpeg: str,
    on_progress: Callable[[int, int], None] | None = None,
) -> dict:
    """يرندر المشاهد أجزاءً، ويكمل ما بقي، ثم يدمج.

    ``director.render`` is used for one scene at a time (``scene_range``) with
    no audio: the audio is muxed once, at the end, over the joined picture.
    """
    out = Path(out_path)
    pdir = parts_dir(out)
    pdir.mkdir(parents=True, exist_ok=True)
    state = load_state(out)
    if state.get("plan_fingerprint") != plan_fingerprint:
        # a different plan: the parts belong to another episode
        for old in pdir.glob("scene-*.mp4"):
            old.unlink(missing_ok=True)
        state = {"plan_fingerprint": plan_fingerprint, "parts": {}}
    parts_state: dict = dict(state.get("parts") or {})

    started = time.time()
    rendered = 0
    reused = 0
    ordered: list[Path] = []
    for bound in scene_bounds:
        index = int(bound["index"])
        part = pdir / f"scene-{index:03d}.mp4"
        record = parts_state.get(str(index)) or {}
        if (
            part.exists()
            and record.get("frames")
            and record.get("bytes") == part.stat().st_size
        ):
            reused += 1
            ordered.append(part)
            continue
        tmp = pdir / f"scene-{index:03d}.part.mp4"
        if tmp.exists():
            tmp.unlink()
        result = director.render(
            tmp,
            audio=None,
            scene_range=(index, index),
            on_progress=None,
        )
        frames = int(result.get("frames") or 0)
        if not frames or not tmp.exists():
            raise RuntimeError(f"scene {index} produced no frames")
        # the pen events of the part follow it (the writer named them after
        # the temporary file)
        tmp_sfx = tmp.with_suffix(".sfx.json")
        if tmp_sfx.exists():
            tmp_sfx.replace(part.with_suffix(".sfx.json"))
        tmp.replace(part)
        parts_state[str(index)] = {
            "frames": frames,
            "bytes": part.stat().st_size,
            "sha256": sha256_file(part),
        }
        state["parts"] = parts_state
        save_state(out, state)
        rendered += 1
        ordered.append(part)
        if on_progress:
            on_progress(rendered + reused, len(scene_bounds))

    for part in ordered:
        if not part.exists():
            raise RuntimeError(f"missing part: {part}")
    _concat(ordered, out, ffmpeg)

    ordered_with_frames = [
        (
            part,
            int((parts_state.get(str(int(b["index"])) or {}).get("frames") or 0)),
        )
        for part, b in zip(ordered, scene_bounds)
    ]
    events = _merge_events(ordered_with_frames, out)

    total_frames = sum(frames for _, frames in ordered_with_frames)
    return {
        "out": str(out),
        "frames": total_frames,
        "parts": len(ordered),
        "rendered": rendered,
        "reused": reused,
        "events": events,
        "seconds": round(time.time() - started, 1),
        "state": str(state_path(out)),
    }


def clear_parts(out_path: str | Path) -> None:
    """يمسح الأجزاء (بدء نظيف)."""
    pdir = parts_dir(out_path)
    if pdir.exists():
        shutil.rmtree(pdir, ignore_errors=True)
