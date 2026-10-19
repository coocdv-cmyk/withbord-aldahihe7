"""Runs in .venv-gen (torch + diffusers), separate from the renderer.

This worker is intentionally dumb: it loads the already-downloaded local SD1.5
pipeline, generates the requested images, and writes a JSON result. All style,
QA and retry logic lives in the Asset Studio, not here.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path


def main() -> int:
    request_path = Path(sys.argv[1])
    req = json.loads(request_path.read_text(encoding="utf-8"))
    out_dir = Path(req["out_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)

    import torch
    from diffusers import AutoPipelineForText2Image, DPMSolverMultistepScheduler

    torch.set_num_threads(max(1, min(8, int(req.get("threads") or (os.cpu_count() or 4)))))
    model = req.get("model") or "stable-diffusion-v1-5/stable-diffusion-v1-5"
    options = dict(
        torch_dtype=torch.float32,
        local_files_only=True,
        safety_checker=None,
        requires_safety_checker=False,
    )
    try:
        pipe = AutoPipelineForText2Image.from_pretrained(model, variant="fp16", **options)
    except OSError:
        pipe = AutoPipelineForText2Image.from_pretrained(model, **options)
    pipe.scheduler = DPMSolverMultistepScheduler.from_config(pipe.scheduler.config)
    pipe.set_progress_bar_config(disable=True)
    try:
        pipe.enable_attention_slicing()
    except Exception:
        pass

    prompt = str(req.get("prompt") or "").strip()
    negative = str(req.get("negative") or "").strip()
    width = max(256, int(req.get("width") or 512) // 8 * 8)
    height = max(256, int(req.get("height") or 512) // 8 * 8)
    steps = max(1, min(60, int(req.get("steps") or 20)))
    guidance = float(req.get("guidance") or 7.0)
    count = max(1, min(4, int(req.get("count") or 1)))
    seed0 = int(req.get("seed") or 42)
    prefix = str(req.get("prefix") or "sd15")

    tokenizer = pipe.tokenizer
    tokens = len(tokenizer(prompt, truncation=False, add_special_tokens=True).input_ids)
    token_limit = 77

    started = time.perf_counter()
    images: list[str] = []
    with torch.inference_mode():
        for i in range(count):
            seed = seed0 + i
            generator = torch.Generator("cpu").manual_seed(seed)
            image = pipe(
                prompt=prompt,
                negative_prompt=negative,
                num_inference_steps=steps,
                guidance_scale=guidance,
                width=width,
                height=height,
                generator=generator,
            ).images[0]
            path = out_dir / f"{prefix}_{seed}.png"
            image.save(path)
            images.append(str(path))

    result = {
        "ok": True,
        "model": model,
        "device": "cpu",
        "prompt": prompt,
        "negative": negative,
        "prompt_tokens": tokens,
        "token_limit": token_limit,
        "truncated": tokens > token_limit,
        "width": width,
        "height": height,
        "steps": steps,
        "guidance": guidance,
        "count": count,
        "seeds": [seed0 + i for i in range(count)],
        "images": images,
        "seconds": round(time.perf_counter() - started, 2),
    }
    (out_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "seconds": result["seconds"], "images": images}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
