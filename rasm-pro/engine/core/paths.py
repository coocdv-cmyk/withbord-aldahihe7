"""مسارات المشروع وبنية المجلدات."""
from __future__ import annotations

from pathlib import Path

# جذر rasm-pro (ثلاثة مجلدات لأعلى من engine/core/paths.py)
ROOT = Path(__file__).resolve().parents[2]

# مجلدات المشروع
ASSETS = ROOT / "assets"
FONTS = ASSETS / "fonts"
LIBRARY = ROOT / "library"          # مكتبة الأصول القديمة (iconify) — القراءة فقط
CACHE = ROOT / "cache"              # كاش عام (وسائط، مسارات، تحويلات)
PROJECTS = ROOT / "projects"        # مشاريع الفيديوهات
STYLE_PACKS = ROOT / "style_packs"
TOOLS = ROOT / "tools"
LOGS = ROOT / "logs"

CONFIG_FILE = ROOT / "config.json"
CONFIG_EXAMPLE = ROOT / "config.example.json"

for _d in (ASSETS, FONTS, CACHE, PROJECTS, STYLE_PACKS, LOGS):
    _d.mkdir(parents=True, exist_ok=True)

# مجلدات المشروع الفرعية
PROJECT_SUBDIRS = (
    "script",      # النص الأصلي + التحليل
    "research",    # نتائج البحث والتحقق
    "assets",      # الأصول المنزّلة/المصنوعة
    "strokes",     # ملفات المسارات .rstrokes.json
    "audio",       # التعليق الصوتي والموسيقى
    "frames",      # إطارات الرندر (مؤقتة)
    "renders",     # المخرجات النهائية
    "reports",     # تقارير الرندر والنقد
)


def project_dir(project_id: str) -> Path:
    """مجلد مشروع معين (يُنشأ عند الطلب)."""
    d = PROJECTS / project_id
    d.mkdir(parents=True, exist_ok=True)
    for sub in PROJECT_SUBDIRS:
        (d / sub).mkdir(exist_ok=True)
    return d


def cache_dir(*parts: str) -> Path:
    d = CACHE.joinpath(*parts)
    d.mkdir(parents=True, exist_ok=True)
    return d


def cache_file(*parts: str) -> Path:
    """مسار ملف داخل الكاش (ينشئ الأب)."""
    p = CACHE.joinpath(*parts)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p
