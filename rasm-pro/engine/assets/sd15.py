"""Optional local Stable Diffusion 1.5 backend.

The renderer does not import torch. This module launches the existing
`.venv-gen` Python environment as a subprocess, caches results by request hash,
and returns image paths. If the environment/model is missing, callers fall back
to procedural generation.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from ..core.paths import CACHE

ROOT = Path(__file__).resolve().parents[3]
VENV_GEN = ROOT / ".venv-gen"
PYTHON = VENV_GEN / "Scripts" / "python.exe"
WORKER = Path(__file__).resolve().parent / "sd15_worker.py"
CACHE_ROOT = CACHE / "assets" / "sd15"


def model_cache() -> Path:
    return Path.home() / ".cache" / "huggingface" / "hub" / "models--stable-diffusion-v1-5--stable-diffusion-v1-5"


def probe() -> dict:
    cache = model_cache()
    snapshot = None
    if cache.exists():
        for p in (cache / "snapshots").glob("*/model_index.json"):
            snapshot = p
            break
    return {
        "python": str(PYTHON),
        "python_exists": PYTHON.exists(),
        "worker_exists": WORKER.exists(),
        "model_cache": str(cache),
        "model_index": str(snapshot) if snapshot else None,
        "available": bool(PYTHON.exists() and WORKER.exists() and snapshot),
    }


def _key(req: dict) -> str:
    raw = json.dumps(req, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:24]


def generate(req: dict, *, timeout: int | None = None, force: bool = False) -> tuple[list[Path], dict]:
    """Generate via the isolated .venv-gen worker. Returns (paths, result)."""
    info = probe()
    if not info["available"]:
        raise RuntimeError(
            "SD1.5 is not available locally. Need .venv-gen, diffusers, and the "
            f"cached pipeline. Probe: {info}"
        )
    if req.get("width", 512) < 256 or req.get("height", 512) < 256:
        raise ValueError("SD1.5 width/height must be >= 256")

    key = _key(req)
    out_dir = CACHE_ROOT / key
    out_dir.mkdir(parents=True, exist_ok=True)
    result_path = out_dir / "result.json"
    if result_path.exists() and not force:
        result = json.loads(result_path.read_text(encoding="utf-8"))
        paths = [Path(p) for p in result.get("images", []) if Path(p).exists()]
        if paths:
            return paths, result

    request_path = out_dir / "request.json"
    payload = dict(req)
    payload["out_dir"] = str(out_dir)
    request_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if timeout is None:
        timeout = max(300, 180 + 260 * int(req.get("count", 1)))
    cmd = [str(PYTHON), str(WORKER), str(request_path)]
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip()[-2000:]
        raise RuntimeError(f"SD1.5 worker failed ({proc.returncode}): {tail}")
    if not result_path.exists():
        raise RuntimeError(f"SD1.5 worker produced no result.json: {(proc.stderr or proc.stdout)[-1000:]}")
    result = json.loads(result_path.read_text(encoding="utf-8"))
    paths = [Path(p) for p in result.get("images", []) if Path(p).exists()]
    if not paths:
        raise RuntimeError("SD1.5 worker returned no images")
    return paths, result
