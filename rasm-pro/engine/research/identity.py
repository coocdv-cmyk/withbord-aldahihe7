"""Identity, chronology and name helpers for evidence-based research.

The helpers here deliberately avoid the old shortcuts that damaged historical
research: short names are preserved, BCE years are signed, and centuries are
represented as ranges rather than invented exact years.
"""
from __future__ import annotations

import re
from dataclasses import asdict

from .evidence import Chronology


_CENTURY_RE = re.compile(r"(?i)(?:^|[^a-z])(\d{1,2})(?:st|nd|rd|th)?\s*century")
_CENTURY_AR_RE = re.compile(r"القرن\s*(\d{1,2})")
_BCE_RE = re.compile(r"(?i)(\d{1,4})\s*(?:bce|bc|قبل\s*الميلاد|ق\.م)")
_CE_RANGE_RE = re.compile(r"(-?\d{3,4})\s*(?:[-–—]|to|إلى)\s*(-?\d{3,4})")
_YEAR_RE = re.compile(r"(-?\d{3,4})")


def parse_chronology(text: str | None) -> Chronology:
    raw = (text or "").strip()
    if not raw:
        return Chronology(raw=raw)

    # Century, e.g. "5th century BCE" or "القرن 19".
    m = _CENTURY_RE.search(raw) or _CENTURY_AR_RE.search(raw)
    if m and ("century" in raw.lower() or "القرن" in raw):
        century = int(m.group(1))
        low = raw.lower()
        bce = any(marker in low for marker in ("bce", "bc", "قبل الميلاد", "ق.م"))
        start = -(century * 100) if bce else (century - 1) * 100 + 1
        end = -(century * 100 - 99) if bce else century * 100
        if bce and start > end:
            start, end = end, start
        return Chronology(
            raw=raw,
            era="BCE" if bce else "CE",
            start_year=start,
            end_year=end,
            precision="century",
            approximate=True,
            normalised=f"{century}th century {'BCE' if bce else 'CE'}",
        )

    # Explicit BCE year.
    m = _BCE_RE.search(raw)
    if m:
        year = -int(m.group(1))
        return Chronology(raw=raw, era="BCE", start_year=year, end_year=year,
                          precision="year", normalised=f"{abs(year)} BCE")

    # Range.
    m = _CE_RANGE_RE.search(raw)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        if a > b:
            a, b = b, a
        era = "BCE" if b < 0 else "CE"
        return Chronology(raw=raw, era=era, start_year=a, end_year=b,
                          precision="range", normalised=f"{a} to {b}")

    # Signed or plain year.
    m = _YEAR_RE.search(raw)
    if m:
        year = int(m.group(1))
        era = "BCE" if year < 0 else "CE"
        return Chronology(raw=raw, era=era, start_year=year, end_year=year,
                          precision="year", normalised=str(year))

    return Chronology(raw=raw, era="unknown", precision="unknown", normalised=raw)


def chronology_to_dict(value: Chronology | dict | None) -> dict:
    if value is None:
        return {}
    if isinstance(value, Chronology):
        return value.to_dict() if hasattr(value, "to_dict") else asdict(value)
    return dict(value)


def name_tokens(name: str | None) -> list[str]:
    """Preserve short words such as 'Sun', 'Tzu', 'Art' and 'of'."""
    text = (name or "").strip().lower()
    # Keep Latin and Arabic word characters; do not discard two-letter words.
    return [t for t in re.findall(r"[\w\u0600-\u06ff]{2,}", text)]


def token_overlap(left: str | None, right: str | None) -> float:
    a = set(name_tokens(left))
    b = set(name_tokens(right))
    if not a or not b:
        return 0.0
    return len(a & b) / max(len(a), len(b))


def contains_all_tokens(needle: str | None, haystack: str | None) -> bool:
    n = set(name_tokens(needle))
    h = set(name_tokens(haystack))
    return bool(n) and n.issubset(h)


def signed_year(value: str | int | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if not text:
        return None
    ch = parse_chronology(text)
    if ch.start_year is not None:
        return ch.start_year
    m = _YEAR_RE.search(text)
    return int(m.group(1)) if m else None


def year_in_chronology(year: int | None, chronology: Chronology | dict | None) -> bool:
    ch = chronology if isinstance(chronology, Chronology) else None
    if ch is None and isinstance(chronology, dict):
        ch = Chronology(**{k: v for k, v in chronology.items() if k in Chronology.__dataclass_fields__})
    if ch is None or year is None or ch.start_year is None:
        return False
    end = ch.end_year if ch.end_year is not None else ch.start_year
    lo, hi = sorted((ch.start_year, end))
    return lo <= year <= hi
