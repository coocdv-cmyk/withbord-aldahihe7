"""Locked visual style packs for generated assets."""
from __future__ import annotations

import json
from pathlib import Path

from ..core.paths import STYLE_PACKS

DEFAULT_STYLE = "paper_ink_v1"


def load_style(name: str | Path | None = None) -> dict:
    """Load a style pack by id or path. Raises a clear error if missing."""
    if name is None:
        name = DEFAULT_STYLE
    p = Path(name)
    if not p.exists():
        p = STYLE_PACKS / f"{name}.json"
    if not p.exists():
        raise FileNotFoundError(
            f"Style pack not found: {name!r}. Expected {STYLE_PACKS / (str(name) + '.json')}"
        )
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "kinds" not in data:
        raise ValueError(f"Invalid style pack: {p}")
    data.setdefault("id", p.stem)
    data.setdefault("palette", {})
    data.setdefault("qa", {})
    data["_path"] = str(p)
    return data


def hex_rgb(value: str) -> tuple[int, int, int]:
    value = str(value).strip().lstrip("#")
    if len(value) == 3:
        value = "".join(c * 2 for c in value)
    if len(value) != 6:
        raise ValueError(f"Invalid color: {value!r}")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))


def palette_colors(style: dict) -> dict[str, list[tuple[int, int, int]]]:
    out: dict[str, list[tuple[int, int, int]]] = {}
    for group, values in (style.get("palette") or {}).items():
        if isinstance(values, list):
            out[group] = [hex_rgb(v) for v in values]
    return out


def all_palette(style: dict) -> list[tuple[int, int, int]]:
    seen: list[tuple[int, int, int]] = []
    for values in palette_colors(style).values():
        for c in values:
            if c not in seen:
                seen.append(c)
    return seen


def find_asset_font() -> str | None:
    """Best available UI font for contact sheets (never fails)."""
    from ..core.paths import FONTS

    for name in ("inter", "cairo", "amiri", "arefruqaa"):
        d = FONTS / name
        if d.is_dir():
            files = sorted(d.glob("*.ttf"))
            if not files:
                continue
            def _score(p: Path) -> int:
                n = p.name.lower()
                score = 0
                if "italic" not in n and "oblique" not in n:
                    score += 10
                if "[" not in n:
                    score += 4
                if "regular" in n:
                    score += 3
                if "bold" in n:
                    score -= 2
                return score
            return str(max(files, key=_score))
    return None
