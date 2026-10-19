"""محرك المسارات: SVG/صور/نص → مسارات رسم متجهية + معاينة."""
from .model import ENGINE_VERSION, Stroke, StrokeDoc, simplify_stroke, stroke_cache_path  # noqa: F401
from .hand_order import order_mask_paths  # noqa: F401
from .hand_timeline import HandTimeline, PenEvent  # noqa: F401
from .order import order_reading, order_strokes, order_travel  # noqa: F401
from .preview import render_preview, render_strip  # noqa: F401
from .raster import raster_to_strokes  # noqa: F401
from .svg_scan import scan_svg  # noqa: F401
from .text_paths import find_font, list_fonts, text_to_strokes  # noqa: F401
from .thinning import thin  # noqa: F401

__all__ = [
    "Stroke",
    "StrokeDoc",
    "simplify_stroke",
    "stroke_cache_path",
    "scan_svg",
    "raster_to_strokes",
    "text_to_strokes",
    "find_font",
    "list_fonts",
    "order_strokes",
    "order_reading",
    "order_travel",
    "render_preview",
    "render_strip",
    "thin",
    "ENGINE_VERSION",
]
