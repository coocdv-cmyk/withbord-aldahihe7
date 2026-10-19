"""بوابة الترخيص: قرار آلي لكل أصل يدخل المشروع + شروط النسب."""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict

# أنماط سماح بمستويات
CORE_ALLOW = [
    r"public domain", r"\bpd[- ]", r"pd-", r"cc0", r"no known copyright", r"no restrictions",
    r"publicdomain", r"crown copyright expired", r"بلا قيود", r"ملكية عامة",
]
ATTR_ALLOW = [
    r"cc[ -]?by[ -]?[1-4]?(\.\d)?\b", r"creative commons attribution(?!.*share)",
    r"cc[ -]?by$",
]
SHAREALIKE = [r"cc[ -]?by[ -]?sa", r"share[- ]?alike", r"cc[ -]?by[ -]?sa[ -]?[1-4]"]
DENY = [
    r"non[- ]?commercial", r"\bnc\b", r"cc[ -]?by[ -]?nc", r"-nc", r"_nc",
    r"no ?deriv", r"\bnd\b", r"cc[ -]?by[ -]?nd",
    r"fair use", r"all rights reserved", r"©", r"copyright(?! expired)",
    r"gfdl", r"noncommercial", r"educational use only", r"permission", r"unknown", r"غير معروف",
]


@dataclass
class LicenseDecision:
    allow: bool
    level: str                 # core | attribution | sharealike | deny
    needs_attribution: bool
    sharealike: bool
    reason: str

    def dict(self) -> dict:
        return asdict(self)


def classify_license(name: str | None, url: str | None = None, *, allow_sharealike: bool = True,
                     usage_terms: str | None = None) -> LicenseDecision:
    """يصنّف نص الرخصة إلى قرار قابل للتنفيذ."""
    raw = " ".join(x for x in [name or "", usage_terms or "", url or ""] if x).strip()
    low = raw.lower()

    if not low:
        return LicenseDecision(False, "deny", False, False, "لا توجد بيانات رخصة")

    for pat in DENY:
        if re.search(pat, low):
            # استثناء: "cc by" لا يحتوي nc/nd — الفحص أعلاه يمنع الخلط
            if re.search(r"cc[ -]?by[ -]?sa", low) and not re.search(r"nc|non[- ]?commercial|\bnd\b", low):
                continue
            return LicenseDecision(False, "deny", False, False, f"رخصة ممنوعة/غير واضحة: {name}")

    for pat in CORE_ALLOW:
        if re.search(pat, low):
            return LicenseDecision(True, "core", False, False, f"ملكية عامة/CC0: {name}")

    for pat in SHAREALIKE:
        if re.search(pat, low):
            if allow_sharealike:
                return LicenseDecision(True, "sharealike", True, True, f"CC BY-SA (نسبة + مشاركة بالمثل): {name}")
            return LicenseDecision(False, "deny", False, False, "CC BY-SA غير مسموح في الإعدادات")

    for pat in ATTR_ALLOW:
        if re.search(pat, low):
            return LicenseDecision(True, "attribution", True, False, f"CC BY (نسبة إلزامية): {name}")

    # رخص برمجية/أصول رقمية
    if re.search(r"mit|apache|isc|bsd|unlicense|ofl", low):
        return LicenseDecision(True, "attribution", True, False, f"رخصة برمجية/خطوط مسموحة: {name}")

    return LicenseDecision(False, "deny", False, False, f"رخصة غير محددة القبول: {name}")


def format_credit(title: str, author: str | None, source: str, license_name: str, source_url: str) -> str:
    who = f" — {author}" if author else ""
    return f"- **{title}**{who} · {source} · {license_name} · {source_url}"
