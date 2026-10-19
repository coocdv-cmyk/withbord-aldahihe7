"""Asset Studio: deterministic paper/collage assets + optional local SD1.5.

The renderer never depends on a model. Asset Studio is an optional production
layer that creates backgrounds, cards, scraps and overlays in the project's
locked visual style, validates them, and keeps provenance for review.

Imports are lazy so ``python -m engine.assets.studio`` does not trigger a
circular import while the package is being initialized.
"""
from __future__ import annotations

__all__ = ["AssetRequest", "AssetStudio", "generate_assets"]


def __getattr__(name: str):
    if name in __all__:
        from . import studio as _studio
        return getattr(_studio, name)
    raise AttributeError(name)
