"""مسارات المشروع والبرنامج.

في الكود المصدري، جذر البيانات هو ``rasm-pro`` نفسه. في النسخة المحزومة
(one-folder) يصبح جذر البيانات مجلدًا بجانب التنفيذي، بينما تبقى الأصول
المقروءة فقط (الخطوط وأقلام الرسم) داخل حزمة PyInstaller. يمكن دائمًا تغيير
مكان البيانات عبر ``RASM_HOME`` من دون إعادة بناء البرنامج.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

FROZEN = bool(getattr(sys, "frozen", False))

# الأصول المقروءة فقط التي تُحزم مع الكود (fonts / pen / style templates).
BUNDLE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))

# البيانات القابلة للكتابة: المشاريع، الكاش، السجلات، الإعدادات.
_DEFAULT_DATA = Path(sys.executable).resolve().parent if FROZEN else BUNDLE
ROOT = Path(os.environ.get("RASM_HOME") or _DEFAULT_DATA).resolve()

ASSETS = BUNDLE / "assets"
FONTS = ASSETS / "fonts"
LIBRARY = ROOT / "library"          # مكتبة الأصول القديمة (iconify) — القراءة فقط
CACHE = ROOT / "cache"              # كاش عام (وسائط، مسارات، تحويلات)
PROJECTS = ROOT / "projects"        # مشاريع الفيديوهات
STYLE_PACKS = ROOT / "style_packs"        # حزم الأنماط القابلة للاستبدال من المستخدم
BUNDLE_STYLE_PACKS = BUNDLE / "style_packs"  # حزم الأنماط المرفقة داخل الحزمة
TOOLS = BUNDLE / "tools"
LOGS = ROOT / "logs"

CONFIG_FILE = ROOT / "config.json"
CONFIG_EXAMPLE = BUNDLE / "config.example.json"

for _d in (LIBRARY, CACHE, PROJECTS, STYLE_PACKS, LOGS):
    _d.mkdir(parents=True, exist_ok=True)

# مسارات المشروع الفرعية
PROJECT_SUBDIRS = (
    "script",      # النص الخام + التحليل
    "research",    # مصادر البحث والحقائق
    "assets",      # الأصول المستخدمة/المنشأة
    "strokes",     # ملفات المسارات .rstrokes.json
    "audio",       # التعليق الصوتي والمؤثرات
    "frames",      # إطارات الفيديو (مؤقتة)
    "renders",     # المخرجات النهائية
    "reports",     # تقارير الفحص والتحقق
)


def project_dir(project_id: str) -> Path:
    """مجلد مشروع مركّب (ينشئه عند الحاجة)."""
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
    """مسار ملف داخل الكاش (ينشئ الأب عند الحاجة)."""
    p = CACHE.joinpath(*parts)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p
