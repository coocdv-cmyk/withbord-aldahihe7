"""Regression: cumulative speech time must map to recording time, pauses included.

When the measured number of utterances differs from the number of scenes the
old code accumulated *spoken* samples and then snapped the result to a pause
edge.  That discarded every pause before the boundary, so a mid-episode scene
started too early.  These tests pin the mapping itself, not just monotonicity.
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from engine.audio.align import LEVEL_SEGMENTED, measured_align

RATE = 1000


def _tone(seconds: float, amp: float = 0.3) -> np.ndarray:
    t = np.arange(int(round(seconds * RATE))) / RATE
    return (amp * np.sin(2 * math.pi * 220 * t)).reshape(1, -1)


def _silence(seconds: float) -> np.ndarray:
    return np.zeros((1, int(round(seconds * RATE))))


def _recording() -> np.ndarray:
    # 3 utterances of 1 s, separated by 2 s pauses: speech=3 s, recording=7 s.
    return np.concatenate(
        [_tone(1.0), _silence(2.0), _tone(1.0), _silence(2.0), _tone(1.0)], axis=1
    )


def _scenes(n: int, words: int = 6) -> list[dict]:
    return [{"id": i + 1, "narration": " ".join(["كلمة"] * words)} for i in range(n)]


def test_mismatch_maps_through_pauses_instead_of_compressing_speech():
    audio = _recording()
    al = measured_align(_scenes(2), audio, RATE, audio.shape[1])
    assert al.level == LEVEL_SEGMENTED
    # Equal text weights => the boundary is halfway through the *spoken* time
    # (1.5 s of speech), which lands 0.5 s into the second utterance.
    # The second utterance starts at 3.0 s in the recording, so the boundary
    # must be 3.5 s, not the old 1.0 s (the nearest pause edge to 1.5 s).
    assert al.segments[1].start_sample == pytest.approx(3.5 * RATE, abs=2)
    # Every pause before that boundary is accounted for by the mapping.
    assert al.segments[1].start_sample > 3.0 * RATE


def test_more_scenes_than_utterances_still_covers_the_recording():
    audio = _recording()
    al = measured_align(_scenes(5), audio, RATE, audio.shape[1])
    starts = [s.start_sample for s in al.segments]
    ends = [s.end_sample for s in al.segments]
    assert starts[0] == 0
    assert ends[-1] == audio.shape[1]
    assert all(a < b for a, b in zip(starts, starts[1:]))
    assert all(a < b for a, b in zip(ends, ends[1:]))
    assert all(end == next_start for end, next_start in zip(ends, starts[1:]))
    # The 4 s of silence cannot vanish: the five scene spans still total 7 s.
    assert sum(s.length for s in al.segments) == audio.shape[1]


def test_text_weight_moves_the_boundary_later():
    audio = _recording()
    scenes = [
        {"id": 1, "narration": " ".join(["طويل"] * 30)},
        {"id": 2, "narration": "قصير"},
    ]
    al = measured_align(scenes, audio, RATE, audio.shape[1])
    # A much longer first scene gets more speech time, so the boundary moves
    # past the midpoint of the spoken timeline (1.5 s) into the third
    # utterance; in the recording that is past 3.5 s, never compressed to 1 s.
    assert al.segments[1].start_sample > 3.5 * RATE


def test_boundary_lands_in_a_pause_when_the_target_is_a_pause():
    audio = _recording()
    # Two scenes weighted so the first boundary falls exactly at the end of
    # the first utterance: it must stay at 1.0 s rather than drift into speech.
    scenes = [
        {"id": 1, "narration": " ".join(["أ"] * 10)},
        {"id": 2, "narration": " ".join(["ب"] * 20)},
    ]
    al = measured_align(scenes, audio, RATE, audio.shape[1])
    first = al.segments[0]
    assert first.end_sample == pytest.approx(1.0 * RATE, abs=3)


def test_zero_length_scene_is_never_created_by_pause_mapping():
    audio = _recording()
    al = measured_align(_scenes(30), audio, RATE, audio.shape[1])
    assert all(s.end_sample > s.start_sample for s in al.segments)
    assert all(
        next_s.start_sample == s.end_sample for s, next_s in zip(al.segments, al.segments[1:])
    )
