"""Regression: الرندر **قابل للاستئناف** — كالرشد في المنعطفات.

لماذا: رندر 25 دقيقة في طلقة واحدة يعني أن أي انهيار يمحو ساعة عمل. الآن
كل مشهد جزءٌ على القرص، و��عادة التشغيل تكمل ما بقي فقط.

* الرندر بالأجزاء = الرندر المباشر: نفس الإطارات ونفس المدة بالضبط.
* إعادة التشغيل **تعيد استعمال** الأجزاء المنجزة (أسرع) وتكتب نفس النتيجة.
* جزء مفقود ⇒ يُرندر وحده، والباقي يُستعمل كما هو.
* الخطة تغيّرت ⇒ الأجزاء القديمة تُهمَل (بصمة الخطة في الحالة).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import requires_ffmpeg, requires_ffprobe
from engine.production import render_production
from engine.render.parts import load_state, parts_dir, state_path


def _plan(scenes: int = 3) -> dict:
    out = []
    frame = 0
    for index in range(1, scenes + 1):
        frames = 36
        out.append(
            {
                "id": index,
                "duration": frames / 24,
                "narration": f"Scene number {index} with a short line of text.",
                "role": "explain",
                "needs": [],
                "elements": [
                    {
                        "type": "text",
                        "text": f"Scene {index}",
                        "font": "inter",
                        "size": 120,
                        "rect": [130, 380, 2300, 700],
                        "mode": "skeleton",
                        "rtl": False,
                        "color": "#211E1A",
                    }
                ],
                "start_frame": frame,
                "end_frame": frame + frames,
                "duration_frames": frames,
            }
        )
        frame += frames
    return {
        "fps": {"num": 24, "den": 1},
        "canvas": [2560, 1440],
        "lang": "en",
        "audio": None,
        "scenes": out,
        "stats": {"frames": frame, "duration": frame / 24},
    }


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    pd = tmp_path / "resume-project"
    (pd / "storyboard").mkdir(parents=True)
    return pd


@requires_ffmpeg
@requires_ffprobe
def test_the_parts_render_matches_the_direct_render(project: Path):
    direct = render_production(
        project, _plan(), mode="final", size=(160, 90), sfx=False, resumable=False
    )
    parts = render_production(
        project, _plan(), mode="final", size=(160, 90), sfx=False, resumable=True
    )
    assert direct["frames"] == parts["frames"], (direct["frames"], parts["frames"])
    assert direct["duration_sec_exact"] == parts["duration_sec_exact"]
    assert parts["resumable"] is True
    assert parts["parts"] == 3


@requires_ffmpeg
@requires_ffprobe
def test_a_second_run_reuses_the_finished_parts(project: Path):
    first = render_production(
        project, _plan(), mode="final", size=(160, 90), sfx=False, resumable=True
    )
    assert first["rendered"] == 3
    assert first["reused"] == 0
    second = render_production(
        project, _plan(), mode="final", size=(160, 90), sfx=False, resumable=True
    )
    assert second["reused"] == 3
    assert second["rendered"] == 0
    assert second["frames"] == first["frames"]


@requires_ffmpeg
@requires_ffprobe
def test_a_missing_part_is_rendered_again(project: Path):
    render_production(project, _plan(), mode="final", size=(160, 90), sfx=False, resumable=True)
    state = load_state(project / "render" / "episode.mp4")
    victim = parts_dir(project / "render" / "episode.mp4") / "scene-002.mp4"
    victim.unlink()
    again = render_production(
        project, _plan(), mode="final", size=(160, 90), sfx=False, resumable=True
    )
    assert again["rendered"] == 1
    assert again["reused"] == 2
    assert again["frames"] == 108


@requires_ffmpeg
@requires_ffprobe
def test_a_different_plan_discards_the_old_parts(project: Path):
    render_production(project, _plan(), mode="final", size=(160, 90), sfx=False, resumable=True)
    other = render_production(
        project, _plan(scenes=2), mode="final", size=(160, 90), sfx=False, resumable=True
    )
    assert other["rendered"] == 2
    assert other["frames"] == 72
    state = json.loads(state_path(project / "render" / "episode.mp4").read_text(encoding="utf-8"))
    assert set(state["parts"]) == {"1", "2"}
