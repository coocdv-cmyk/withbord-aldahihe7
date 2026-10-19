"""كاتب الفيديو: تدفّق إطارات rawvideo إلى ffmpeg (نستخدم ffmpeg المدمج في studio)."""
from __future__ import annotations

import subprocess
from pathlib import Path

from PIL import Image

FFMPEG_CANDIDATES = (
    Path(r"D:\withbord inmation\studio\runtime\ffmpeg.exe"),
    Path("ffmpeg"),
)


def ffmpeg_path() -> str:
    for c in FFMPEG_CANDIDATES:
        if str(c) == "ffmpeg" or c.exists():
            return str(c)
    return "ffmpeg"


class FFmpegWriter:
    """يكتب إطارات RGB خام مباشرة إلى أنبوب ffmpeg (سريع بلا ملفات وسيطة)."""

    def __init__(
        self,
        out_path: str | Path,
        size: tuple[int, int],
        *,
        fps: int = 30,
        crf: int = 19,
        preset: str = "medium",
        audio: str | Path | None = None,
        ffmpeg: str | None = None,
    ):
        self.size = (int(size[0]), int(size[1]))
        self.fps = int(fps)
        self.frames = 0
        self.out = str(out_path)
        Path(self.out).parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            ffmpeg or ffmpeg_path(),
            "-y",
            "-loglevel", "error",
            "-f", "rawvideo",
            "-pix_fmt", "rgb24",
            "-s", f"{self.size[0]}x{self.size[1]}",
            "-r", str(self.fps),
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
            cmd += ["-c:a", "aac", "-b:a", "192k", "-shortest"]
        cmd += [self.out]
        self.cmd = cmd
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

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
        return rc
