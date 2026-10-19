"""Asset Studio orchestration: generate → post-process → QA → review.

The studio is the "brain" around the optional SD1.5 model:

* chooses a procedural or SD1.5 backend;
* falls back to procedural if the model is unavailable or fails QA;
* converts every result to the locked paper/ink palette;
* measures palette distance, saturation, text-zone clutter, faces and alpha;
* prepares a clean text-safe zone;
* saves metadata, hashes, provenance and a human-review contact sheet.

The renderer remains model-free. Assets are ordinary PNG files that a plan can
reference with a ``texture``/``background`` element or a ``paper_card`` texture.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image

from ..core.paths import ASSETS
import engine.assets.brain as brain
import engine.assets.procedural as procedural
import engine.assets.sd15 as sd15
from .post import (
    add_grain,
    add_vignette,
    clean_text_zone,
    contact_sheet,
    cut_flat_background,
    resize_cover,
    tone_to_palette,
)
from .qa import analyze, hamming
from .style import DEFAULT_STYLE, find_asset_font, load_style, palette_colors

RASM_ROOT = Path(__file__).resolve().parents[2]
GENERATED = ASSETS / "generated"
MANIFEST = GENERATED / "manifest.json"
APPROVALS = GENERATED / "approved.json"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _parse_size(value: Any) -> tuple[int, int]:
    if isinstance(value, (tuple, list)) and len(value) == 2:
        return int(value[0]), int(value[1])
    m = re.search(r"(\d+)\s*[xX×]\s*(\d+)", str(value))
    if not m:
        raise ValueError(f"Invalid size {value!r}; use WIDTHxHEIGHT, e.g. 2560x1440")
    return int(m.group(1)), int(m.group(2))


def _parse_zone(value: Any) -> tuple[float, float, float, float] | None:
    if value in (None, ""):
        return None
    if isinstance(value, (tuple, list)) and len(value) == 4:
        return tuple(float(v) for v in value)  # type: ignore[return-value]
    parts = [p for p in re.split(r"[,; ]+", str(value).strip()) if p]
    if len(parts) != 4:
        raise ValueError("text zone must be x,y,w,h in 0..1, e.g. 0.16,0.16,0.68,0.58")
    out = tuple(float(p) for p in parts)
    if any(v < 0 or v > 1 for v in out):
        raise ValueError("text zone values must be between 0 and 1")
    return out  # type: ignore[return-value]


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(RASM_ROOT))
    except ValueError:
        return str(path.resolve())


def _abs(path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else (RASM_ROOT / p)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class AssetRequest:
    kind: str
    purpose: str | None = None
    size: tuple[int, int] | str = (2560, 1440)
    count: int = 3
    seed: int = 42
    style: str = DEFAULT_STYLE
    method: str = "auto"  # auto | procedural | sd15
    text_safe_zone: tuple[float, float, float, float] | str | None = None
    clean_text_zone: bool = True
    seamless: bool = False
    output_dir: str | Path | None = None
    prompt: str | None = None
    negative: str | None = None
    steps: int = 20
    guidance: float = 7.0
    max_candidates: int | None = None
    force: bool = False
    timeout: int | None = None
    allow_fail: bool = False

    def __post_init__(self) -> None:
        self.size = _parse_size(self.size)
        self.text_safe_zone = _parse_zone(self.text_safe_zone)
        self.count = max(1, int(self.count))
        self.steps = max(1, min(60, int(self.steps)))
        self.guidance = float(self.guidance)
        if self.purpose is not None:
            self.purpose = str(self.purpose).strip().lower()
        if self.output_dir is not None:
            self.output_dir = Path(self.output_dir)


class AssetStudio:
    def __init__(self, style: str = DEFAULT_STYLE):
        self.style = load_style(style)
        self.style_id = str(self.style.get("id") or Path(self.style.get("_path", style)).stem)
        self.root = GENERATED / self.style_id
        self.manifest_path = MANIFEST
        self.approvals_path = APPROVALS

    # ------------------------------------------------------------------
    # public
    # ------------------------------------------------------------------
    def kinds(self) -> dict:
        return dict(self.style.get("kinds") or {})

    def generate(self, req: AssetRequest) -> dict:
        kinds = self.kinds()
        if req.kind not in kinds:
            raise KeyError(
                f"Unknown kind {req.kind!r}. Run `python -m engine.assets.studio kinds` "
                f"to see {len(kinds)} available kinds."
            )
        spec = dict(kinds[req.kind] or {})
        purpose = req.purpose or str(spec.get("purpose") or "background")
        zone = req.text_safe_zone or tuple(float(v) for v in (self.style.get("text_safe_zone") or (0.16, 0.16, 0.68, 0.58)))
        method, fallback_kind, requested_method, note = self._resolve_method(req, spec)
        gen_kind = fallback_kind if method == "procedural-fallback" and fallback_kind else req.kind
        gen_spec = dict(kinds.get(gen_kind) or spec)
        max_candidates = req.max_candidates
        if max_candidates is None:
            if method == "sd15":
                max_candidates = max(1, min(3, req.count))
            else:
                max_candidates = max(req.count * 2, 4)
        max_candidates = max(1, int(max_candidates))

        candidates: list[dict] = []
        failures: list[str] = []
        for i in range(max_candidates):
            seed = int(req.seed) + i * 101
            try:
                img, info = self._generate_one(gen_kind, method, req, gen_spec, seed)
                img, clean_info = self._prepare(img, req, gen_spec, purpose, zone, seed)
                qa = analyze(img, self.style, gen_spec, purpose=purpose, zone=zone)
                min_score = float((self.style.get("qa") or {}).get("min_score", 52.0))
                if qa["score"] < min_score:
                    qa["failures"].append(f"score {qa['score']} < {min_score}")
                    qa["pass"] = False
                if not qa["pass"]:
                    failures.append(f"seed {seed}: QA " + "; ".join(qa["failures"]))
                if any(hamming(qa["phash"], c["qa"]["phash"]) <= 3 for c in candidates):
                    failures.append(f"seed {seed}: duplicate perceptual hash")
                    continue
                candidates.append({
                    "image": img,
                    "qa": qa,
                    "info": info,
                    "seed": seed,
                    "clean": clean_info,
                    "purpose": purpose,
                    "zone": zone,
                    "method": method,
                    "kind": gen_kind,
                })
                if sum(1 for c in candidates if c["qa"]["pass"]) >= req.count:
                    break
            except Exception as exc:  # keep the best diagnostic, do not hide it
                failures.append(f"seed {seed}: {type(exc).__name__}: {exc}")

        passing = [c for c in candidates if c["qa"]["pass"]]
        if not passing and method == "sd15" and fallback_kind:
            # Explicit, visible fallback. The renderer still gets an asset.
            for i in range(max(req.count * 2, 2)):
                seed = int(req.seed) + 10000 + i * 37
                try:
                    img = procedural.generate(fallback_kind, req.size[0], req.size[1], seed, self.style)
                    fb_spec = dict(kinds.get(fallback_kind) or {})
                    img, clean_info = self._prepare(img, req, fb_spec, purpose, zone, seed)
                    qa = analyze(img, self.style, fb_spec, purpose=purpose, zone=zone)
                    min_score = float((self.style.get("qa") or {}).get("min_score", 52.0))
                    if qa["score"] < min_score:
                        qa["failures"].append(f"score {qa['score']} < {min_score}")
                        qa["pass"] = False
                    if not qa["pass"]:
                        failures.append(f"fallback seed {seed}: QA " + "; ".join(qa["failures"]))
                    candidates.append({
                        "image": img,
                        "qa": qa,
                        "info": {"method": "procedural-fallback", "seed": seed, "prompt": None,
                                 "negative": None, "model": None, "fallback_from": "sd15"},
                        "seed": seed,
                        "clean": clean_info,
                        "purpose": purpose,
                        "zone": zone,
                        "method": "procedural-fallback",
                        "kind": fallback_kind,
                    })
                    if qa["pass"]:
                        passing.append(candidates[-1])
                        if len(passing) >= req.count:
                            break
                except Exception as exc:
                    failures.append(f"fallback seed {seed}: {type(exc).__name__}: {exc}")

        if not candidates:
            detail = "; ".join(failures[-6:]) or "generation returned nothing"
            raise RuntimeError(f"No candidate produced for {req.kind!r}: {detail}")
        if not passing:
            if not req.allow_fail:
                detail = "; ".join(failures[-6:]) or "no candidate produced"
                raise RuntimeError(
                    f"No asset passed QA for {req.kind!r} ({method}). {detail}. "
                    "Use --allow-fail to save the best candidate for review, or adjust the style pack."
                )
            passing = sorted(candidates, key=lambda c: c["qa"]["score"], reverse=True)
        else:
            passing = sorted(passing, key=lambda c: c["qa"]["score"], reverse=True)

        root = Path(req.output_dir) if req.output_dir else self.root
        saved: list[dict] = []
        for cand in passing[: req.count]:
            meta = self._save(cand, req, spec, root, requested_method, fallback_kind, note)
            saved.append(meta)
        sheet_path = self._sheet(saved, root, req.kind)
        return {
            "ok": bool(saved),
            "style": self.style_id,
            "kind": req.kind,
            "purpose": purpose,
            "requested_method": requested_method,
            "method": method,
            "fallback_kind": fallback_kind,
            "note": note,
            "count": len(saved),
            "candidates": len(candidates),
            "failures": failures,
            "assets": saved,
            "contact_sheet": str(sheet_path),
        }

    # ------------------------------------------------------------------
    # generation
    # ------------------------------------------------------------------
    def _resolve_method(self, req: AssetRequest, spec: dict) -> tuple[str, str | None, str, str]:
        requested = req.method if req.method != "auto" else str(spec.get("method") or "procedural")
        fallback = spec.get("fallback")
        fallback_kind = str(fallback) if fallback and str(fallback) in procedural.PROCEDURAL_KINDS else None
        if requested == "sd15":
            probe = sd15.probe()
            if not probe["available"]:
                if fallback_kind:
                    return "procedural-fallback", fallback_kind, requested, "SD1.5 unavailable; procedural fallback"
                raise RuntimeError(
                    "SD1.5 is not available locally. Run `python -m engine.assets.studio doctor` "
                    "to see the missing pieces, or use --method procedural."
                )
            return "sd15", None, requested, ""
        if requested == "procedural":
            if req.kind in procedural.PROCEDURAL_KINDS:
                return "procedural", None, requested, ""
            if fallback_kind:
                return "procedural-fallback", fallback_kind, requested, "kind has no procedural implementation"
            raise ValueError(f"{req.kind!r} is not procedural and has no fallback")
        raise ValueError(f"Unknown method: {requested!r}")

    def _generate_one(self, kind: str, method: str, req: AssetRequest, spec: dict, seed: int):
        if method == "procedural":
            img = procedural.generate(kind, req.size[0], req.size[1], seed, self.style)
            return img, {"method": "procedural", "seed": seed, "prompt": None,
                         "negative": None, "model": None}
        if method == "procedural-fallback":
            # The caller passes the fallback kind in `kind` for this branch.
            img = procedural.generate(kind, req.size[0], req.size[1], seed, self.style)
            return img, {"method": "procedural-fallback", "seed": seed, "prompt": None,
                         "negative": None, "model": None}
        if method == "sd15":
            prompt = self._prompt_for(kind, spec, req)
            negative = (req.negative or self.style.get("negative") or "").strip()
            worker_req = {
                "model": "stable-diffusion-v1-5/stable-diffusion-v1-5",
                "prompt": prompt,
                "negative": negative,
                "width": 512,
                "height": 512,
                "steps": req.steps,
                "guidance": req.guidance,
                "seed": seed,
                "count": 1,
                "prefix": f"{kind}_{seed}",
                "threads": 4,
            }
            paths, info = sd15.generate(worker_req, timeout=req.timeout, force=req.force)
            img = Image.open(paths[0]).convert("RGBA")
            return img, {"method": "sd15", "seed": seed, "prompt": prompt,
                         "negative": negative, "model": info.get("model"),
                         "worker": info}
        raise ValueError(method)

    def _prompt_for(self, kind: str, spec: dict, req: AssetRequest) -> str:
        base = (req.prompt or spec.get("prompt") or f"vintage documentary {kind.replace('_', ' ')} asset").strip()
        prefix = (self.style.get("prompt_prefix") or "").strip()
        if prefix and not base.lower().startswith(prefix.lower()[:24]):
            base = f"{prefix}, {base}"
        words = base.split()
        # SD1.5 CLIP truncates at 77 tokens; ~65 words is a safe practical bound.
        if len(words) > 65:
            base = " ".join(words[:65])
        return base

    def _prepare(self, img: Image.Image, req: AssetRequest, spec: dict, purpose: str,
                 zone: tuple[float, float, float, float], seed: int) -> tuple[Image.Image, dict]:
        img = resize_cover(img, req.size[0], req.size[1])
        tone_strength = float(spec.get("tone_strength", 0.55 if purpose != "overlay" else 0.25))
        sat_scale = float(spec.get("saturation_scale", 0.78))
        img = tone_to_palette(img, self.style, strength=tone_strength, saturation_scale=sat_scale)
        img = add_grain(img, amount=float(spec.get("grain", 2.6)), seed=seed + 17)
        img = add_vignette(img, strength=float(spec.get("vignette_strength", 0.06)))
        if bool(spec.get("requires_alpha")):
            alpha_min = img.getchannel("A").getextrema()[0]
            if alpha_min >= 255:
                img = cut_flat_background(img, tolerance=float(spec.get("cut_tolerance", 18.0)))
        paper = (palette_colors(self.style).get("paper") or [(244, 235, 221)])[0]
        if req.clean_text_zone and purpose not in ("overlay", "scrap"):
            max_busy = float((self.style.get("qa") or {}).get("max_text_zone_busy", 0.20))
            img, clean_info = clean_text_zone(
                img, zone, max_busy=max_busy, paper_color=paper,
                strength=float(spec.get("clean_strength", 0.72)),
            )
        else:
            clean_info = {"cleaned": False, "skipped": True}
        if req.seamless:
            # A cheap, deterministic roll+blend is enough for low-contrast paper.
            import numpy as np
            arr = np.asarray(img.convert("RGB"), np.float32)
            h, w = arr.shape[:2]
            rolled = np.roll(arr, (h // 2, w // 2), axis=(0, 1))
            blend = np.clip(1.0 - np.minimum(
                np.minimum(np.arange(w)[None, :], np.arange(w)[::-1][None, :]),
                np.minimum(np.arange(h)[:, None], np.arange(h)[::-1][:, None]),
            ) / 64.0, 0, 1)
            arr = arr * (1 - blend[..., None]) + rolled * blend[..., None]
            out = Image.fromarray(np.clip(arr, 0, 255).astype("uint8"), "RGB").convert("RGBA")
            out.putalpha(img.getchannel("A"))
            img = out
        return img, clean_info

    # ------------------------------------------------------------------
    # persistence
    # ------------------------------------------------------------------
    def _save(self, cand: dict, req: AssetRequest, spec: dict, root: Path,
              requested_method: str, fallback_kind: str | None, note: str) -> dict:
        qa = cand["qa"]
        kind = cand["kind"]
        seed = cand["seed"]
        folder = root / kind
        folder.mkdir(parents=True, exist_ok=True)
        base = f"{kind}_{seed}_{qa['phash'][:6]}"
        asset_id = base
        n = 2
        while (folder / f"{asset_id}.png").exists():
            asset_id = f"{base}_{n}"
            n += 1
        path = folder / f"{asset_id}.png"
        cand["image"].save(path, "PNG")
        info = cand["info"]
        meta = {
            "id": asset_id,
            "kind": kind,
            "requested_kind": req.kind,
            "purpose": cand["purpose"],
            "style": self.style_id,
            "style_path": self.style.get("_path"),
            "method": info.get("method"),
            "requested_method": requested_method,
            "fallback_kind": fallback_kind,
            "fallback_from": info.get("fallback_from"),
            "seed": seed,
            "size": [req.size[0], req.size[1]],
            "created": _now(),
            "file": _rel(path),
            "sha256": _sha256(path),
            "phash": qa["phash"],
            "prompt": info.get("prompt"),
            "negative": info.get("negative"),
            "model": info.get("model"),
            "license": ("SD1.5 output — CreativeML OpenRAIL-M" if info.get("method") == "sd15"
                        else "Project-generated procedural asset"),
            "qa": qa,
            "text_safe_zone": list(cand["zone"]),
            "text_zone_clean": cand["clean"],
            "approved": False,
            "source": "asset-studio",
            "note": note,
        }
        approvals = _read_json(self.approvals_path, {})
        meta["approved"] = bool((approvals or {}).get(asset_id))
        _atomic_write_json(folder / f"{asset_id}.json", meta)
        manifest = _read_json(self.manifest_path, {"version": 1, "assets": []})
        assets = [a for a in (manifest.get("assets") or []) if a.get("id") != asset_id]
        assets.append(meta)
        _atomic_write_json(self.manifest_path, {"version": 1, "updated": _now(), "assets": assets})
        if asset_id not in approvals:
            approvals[asset_id] = False
            _atomic_write_json(self.approvals_path, approvals)
        return meta

    def _sheet(self, saved: list[dict], root: Path, kind: str) -> Path:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = root / "contact_sheets" / f"{stamp}_{kind}.jpg"
        records = []
        for m in saved:
            records.append({**m, "file": str(_abs(m["file"]))})
        return contact_sheet(records, out)

    def list_assets(self, kind: str | None = None, approved: bool | None = None) -> list[dict]:
        manifest = _read_json(self.manifest_path, {"assets": []})
        out = []
        for a in manifest.get("assets") or []:
            if kind and a.get("kind") != kind:
                continue
            if approved is not None and bool(a.get("approved")) != approved:
                continue
            out.append(a)
        return sorted(out, key=lambda a: a.get("created", ""), reverse=True)

    def approve(self, asset_id: str, approved: bool = True, note: str = "") -> dict:
        manifest = _read_json(self.manifest_path, {"assets": []})
        found = None
        for a in manifest.get("assets") or []:
            if a.get("id") == asset_id:
                found = a
                break
        if not found:
            raise KeyError(f"Asset not found: {asset_id}")
        found["approved"] = bool(approved)
        found["approval_note"] = note
        found["approved_at"] = _now()
        _atomic_write_json(self.manifest_path, {**manifest, "updated": _now()})
        meta_path = _abs(found["file"]).with_suffix(".json")
        meta = _read_json(meta_path, {})
        if meta:
            meta.update({"approved": bool(approved), "approval_note": note, "approved_at": found["approved_at"]})
            _atomic_write_json(meta_path, meta)
        approvals = _read_json(self.approvals_path, {})
        approvals[asset_id] = bool(approved)
        _atomic_write_json(self.approvals_path, approvals)
        return found

    def doctor(self) -> dict:
        manifest = _read_json(self.manifest_path, {"assets": []})
        return {
            "style": self.style_id,
            "style_path": self.style.get("_path"),
            "kinds": len(self.kinds()),
            "root": str(self.root),
            "manifest": str(self.manifest_path),
            "manifest_assets": len(manifest.get("assets") or []),
            "font": find_asset_font(),
            "sd15": sd15.probe(),
            "procedural_kinds": sorted(procedural.PROCEDURAL_KINDS),
        }


def generate_assets(kind: str, **kwargs) -> dict:
    style = kwargs.pop("style", DEFAULT_STYLE)
    studio = AssetStudio(style)
    return studio.generate(AssetRequest(kind=kind, style=style, **kwargs))


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------

def _print(obj: Any) -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m engine.assets.studio",
        description="Generate and review paper/collage assets in the locked project style.",
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate", help="generate one or more assets")
    g.add_argument("kind")
    g.add_argument("--purpose", choices=["background", "card", "scrap", "overlay"], default=None)
    g.add_argument("--size", default="2560x1440", help="WIDTHxHEIGHT (default 2560x1440)")
    g.add_argument("--count", type=int, default=3)
    g.add_argument("--seed", type=int, default=42)
    g.add_argument("--style", default=DEFAULT_STYLE)
    g.add_argument("--method", choices=["auto", "procedural", "sd15"], default="auto")
    g.add_argument("--text-zone", default=None, help="x,y,w,h fractions, e.g. 0.16,0.16,0.68,0.58")
    g.add_argument("--no-clean", action="store_true", help="do not soften the text-safe zone")
    g.add_argument("--seamless", action="store_true")
    g.add_argument("--out", default=None, help="output root (default assets/generated/<style>)")
    g.add_argument("--prompt", default=None)
    g.add_argument("--negative", default=None)
    g.add_argument("--steps", type=int, default=20)
    g.add_argument("--guidance", type=float, default=7.0)
    g.add_argument("--max-candidates", type=int, default=None)
    g.add_argument("--timeout", type=int, default=None)
    g.add_argument("--force", action="store_true", help="bypass SD1.5 request cache")
    g.add_argument("--allow-fail", action="store_true", help="save best candidate even if QA fails")

    k = sub.add_parser("kinds", help="list available asset kinds")
    k.add_argument("--style", default=DEFAULT_STYLE)

    l = sub.add_parser("list", help="list generated assets")
    l.add_argument("--kind", default=None)
    l.add_argument("--approved", choices=["yes", "no"], default=None)
    l.add_argument("--style", default=DEFAULT_STYLE)

    a = sub.add_parser("approve", help="approve an asset")
    a.add_argument("id")
    a.add_argument("--note", default="")
    a.add_argument("--style", default=DEFAULT_STYLE)

    r = sub.add_parser("reject", help="reject an asset")
    r.add_argument("id")
    r.add_argument("--note", default="")
    r.add_argument("--style", default=DEFAULT_STYLE)

    d = sub.add_parser("doctor", help="check style pack, SD1.5, cache and folders")
    d.add_argument("--style", default=DEFAULT_STYLE)

    b = sub.add_parser("brain", help="suggest asset kinds for a scene")
    b.add_argument("text")
    b.add_argument("--purpose", choices=["background", "card", "scrap", "overlay"], default="background")

    args = ap.parse_args(argv)
    try:
        if args.cmd == "generate":
            req = AssetRequest(
                kind=args.kind,
                purpose=args.purpose,
                size=args.size,
                count=args.count,
                seed=args.seed,
                style=args.style,
                method=args.method,
                text_safe_zone=args.text_zone,
                clean_text_zone=not args.no_clean,
                seamless=args.seamless,
                output_dir=args.out,
                prompt=args.prompt,
                negative=args.negative,
                steps=args.steps,
                guidance=args.guidance,
                max_candidates=args.max_candidates,
                force=args.force,
                timeout=args.timeout,
                allow_fail=args.allow_fail,
            )
            res = AssetStudio(args.style).generate(req)
            _print({k: res[k] for k in ("ok", "style", "kind", "purpose", "requested_method",
                                        "method", "fallback_kind", "note", "count", "candidates",
                                        "failures", "contact_sheet")})
            for asset in res["assets"]:
                print(f"{asset['id']}  {asset['file']}  score={asset['qa']['score']}  pass={asset['qa']['pass']}")
            return 0
        if args.cmd == "kinds":
            studio = AssetStudio(args.style)
            rows = []
            for name, spec in studio.kinds().items():
                rows.append({
                    "kind": name,
                    "method": spec.get("method", "procedural"),
                    "purpose": spec.get("purpose", "background"),
                    "description": spec.get("description", ""),
                })
            _print({"style": studio.style_id, "kinds": rows})
            return 0
        if args.cmd == "list":
            studio = AssetStudio(args.style)
            approved = None if args.approved is None else (args.approved == "yes")
            _print(studio.list_assets(args.kind, approved))
            return 0
        if args.cmd in ("approve", "reject"):
            studio = AssetStudio(args.style)
            found = studio.approve(args.id, approved=(args.cmd == "approve"), note=args.note)
            _print({"id": found["id"], "approved": found["approved"], "file": found["file"]})
            return 0
        if args.cmd == "doctor":
            _print(AssetStudio(args.style).doctor())
            return 0
        if args.cmd == "brain":
            _print(brain.suggest(args.text, args.purpose))
            return 0
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
