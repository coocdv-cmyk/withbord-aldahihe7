"""Shared pytest configuration.

The renderer writes through ffmpeg and the audio tools probe through
ffprobe.  Both are **external sidecars** in this project (never bundled, see
``docs/08-PACKAGING-ADR-AR.md``), so a machine without them must not turn
into a wall of red failures: the affected tests are skipped explicitly and
the skip is visible in the report.
"""
from __future__ import annotations

import pytest


def _ffmpeg_available() -> bool:
    try:
        from engine.render.video import ffmpeg_path

        return bool(ffmpeg_path())
    except Exception:
        return False


def _ffprobe_available() -> bool:
    try:
        from engine.audio.probe import ffprobe_path

        return bool(ffprobe_path())
    except Exception:
        return False


requires_ffmpeg = pytest.mark.skipif(
    not _ffmpeg_available(), reason="ffmpeg is not available on this machine"
)
requires_ffprobe = pytest.mark.skipif(
    not _ffprobe_available(), reason="ffprobe is not available on this machine"
)
