"""Video writer: raw RGB frames piped to ffmpeg.

The frame rate is a rational ``FrameRate`` (for example ``30000/1001``), never a
rounded float.  When the caller knows the exact frame count we also pass an
explicit output duration and verify it after the pipe closes.  This removes the
old ``-shortest`` behaviour, which could silently trim video when the audio was
slightly shorter.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image

from ..core.timebase import FrameRate, coerce_frame_rate, TimebaseError


def _bundle_roots() -> list[Path]:
    roots: list[Path] = []
    env = os.environ.get("RASM_FFMPEG_DIR")
    if env:
        roots.append(Path(env))
    if getattr(sys, "frozen", False):
        roots.append(Path(sys.executable).resolve().parent / "runtime")
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        roots.append(Path(meipass) / "runtime")
    # Source checkout: rasm-pro/engine/render/video.py → rasm-pro and repo root.
    data_home = os.environ.get("RASM_HOME")
    if data_home:
        roots.append(Path(data_home) / "runtime")
        roots.append(Path(data_home).resolve().parent / "studio" / "runtime")
    here = Path(__file__).resolve()
    roots.append(here.parents[2] / "runtime")
    roots.append(here.parents[3] / "studio" / "runtime")
    return roots


def ffmpeg_path() -> str | None:
    """Locate ffmpeg, or ``None`` when it is not available.

    ffmpeg is an external sidecar in this project (never bundled), so the
    honest answer is "not found" instead of a bare command name that fails
    later with a confusing error.
    """
    env = os.environ.get("RASM_FFMPEG")
    if env and Path(env).exists():
        return str(Path(env))
    for root in _bundle_roots():
        candidate = root / "ffmpeg.exe"
        if candidate.exists():
            return str(candidate)
        candidate = root / "ffmpeg"
        if candidate.exists():
            return str(candidate)
    return shutil.which("ffmpeg")


def require_ffmpeg() -> str:
    """The ffmpeg executable, or an explicit error naming every way to fix it."""
    exe = ffmpeg_path()
    if not exe:
        raise RuntimeError(
            "ffmpeg غير موجود. ضعه في runtime/ بجانب التطبيق أو اضبط "
            "RASM_FFMPEG أو RASM_FFMPEG_DIR أو أضفه إلى PATH."
        )
    return exe


class FFmpegWriter:
    """Writes raw RGB frames directly into an ffmpeg pipe (no temp image files)."""

    def __init__(
        self,
        out_path: str | Path,
        size: tuple[int, int],
        *,
        fps: FrameRate | int | float | str | dict | None = None,
        crf: int = 19,
        preset: str = "medium",
        audio: str | Path | None = None,
        ffmpeg: str | None = None,
        expected_frames: int | None = None,
    ):
        self.size = (int(size[0]), int(size[1]))
        self.fps_rate = coerce_frame_rate(24 if fps is None else fps)
        self.fps = self.fps_rate.fps
        self.expected_frames = int(expected_frames) if expected_frames else None
        if self.expected_frames is not None and self.expected_frames <= 0:
            raise TimebaseError("expected_frames يجب أن يكون موجبًا")
        self.frames = 0
        self.out = str(out_path)
        Path(self.out).parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            ffmpeg or require_ffmpeg(),
            "-y",
            "-loglevel", "error",
            "-f", "rawvideo",
            "-pix_fmt", "rgb24",
            "-s", f"{self.size[0]}x{self.size[1]}",
            "-r", self.fps_rate.ffmpeg,
            "-i", "-",
        ]
        if audio:
            cmd += ["-i", str(audio)]
        cmd += [
            "-c:v", "libx264",
            "-preset", preset,
            "-crf", str(crf),
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
        ]
        if audio:
            cmd += ["-c:a", "aac", "-b:a", "192k"]
        if self.expected_frames is not None:
            duration = self.fps_rate.time_of_frames(self.expected_frames)
            # Exact decimal to nanoseconds; ffmpeg's -t accepts this form.
            cmd += ["-t", f"{float(duration):.9f}"]
        cmd += [self.out]
        self.cmd = cmd
        try:
            self.proc = subprocess.Popen(
                cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                "ffmpeg غير موجود. ضعه في runtime/ بجانب التطبيق أو اضبط "
                "RASM_FFMPEG أو RASM_FFMPEG_DIR أو أضفه إلى PATH."
            ) from exc

    def write(self, img: Image.Image) -> None:
        if img.size != self.size:
            img = img.resize(self.size, Image.BILINEAR)
        if img.mode != "RGB":
            img = img.convert("RGB")
        assert self.proc.stdin is not None
        self.proc.stdin.write(img.tobytes())
        self.frames += 1

    def close(self) -> int:
        if self.proc is None:
            return 0
        try:
            if self.proc.stdin:
                self.proc.stdin.close()
        except Exception:
            pass
        rc = self.proc.wait()
        if rc != 0:
            err = b""
            try:
                err = self.proc.stderr.read() if self.proc.stderr else b""
            except Exception:
                pass
            raise RuntimeError(f"ffmpeg فشل (كود {rc}): {err.decode('utf-8', 'replace')[-600:]}")
        if self.expected_frames is not None and self.frames != self.expected_frames:
            raise RuntimeError(
                f"عدد الإطارات المكتوب ({self.frames}) لا يطابق المتوقع ({self.expected_frames})"
            )
        return rc
