"""أدوات اللغة العربية: تطبيع، تقسيم جُمل، كشف الاتجاه، أرقام، كلمات مفتاحية.""" 
from __future__ import annotations

import re
import unicodedata

ARABIC_RE = re.compile(r"[\u0600-\u06FF]")
DIACRITICS_RE = re.compile(r"[\u064B-\u065F\u0670\u06D6-\u06ED]")
TATWEEL = "\u0640"

# تطبيع: إزالة التشكيل والتطويل وتوحيد الألف والهمزات والياء والتاء المربوطة
_ALEF = re.compile(r"[أإآٱ]")
_YA = re.compile(r"[ىئ]")
_TA = re.compile(r"ة")


def normalize(text: str, keep_diacritics: bool = False) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    if not keep_diacritics:
        text = DIACRITICS_RE.sub("", text)
    text = text.replace(TATWEEL, "")
    text = _ALEF.sub("ا", text)
    text = _YA.sub("ي", text)
    text = _TA.sub("ه", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def is_arabic(text: str, threshold: float = 0.2) -> bool:
    if not text:
        return False
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return False
    ar = sum(1 for c in letters if ARABIC_RE.match(c))
    return ar / len(letters) >= threshold


def strip_diacritics(text: str) -> str:
    return DIACRITICS_RE.sub("", text)


def split_sentences(text: str) -> list[str]:
    """تقسيم الجُمل: يدعم . ! ? ؛ ؟ … والخ.»"""
    text = re.sub(r"\r\n?", "\n", text)
    # توحيد علامات النهاية
    parts = re.split(r"(?<=[.!?؟…])\s+|\n{2,}", text)
    out = []
    for p in parts:
        p = p.strip()
        if p:
            out.append(p)
    return out


def words(text: str) -> list[str]:
    return [w for w in re.split(r"[\s،,؛;:.!?؟…\"'()\[\]{}«»\-–—]+", text) if w]


def word_count(text: str) -> int:
    return len(words(text))


AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def latin_digits(text: str) -> str:
    return text.translate(AR_DIGITS)


def find_numbers(text: str) -> list[str]:
    """أرقام وسنوات ونسب (بالعربية أو اللاتينية) مع علاماتها."""
    t = latin_digits(text)
    pats = [
        r"\b\d{1,3}(?:[.,]\d+)?\s?%",
        r"\b(?:1[0-9]{3}|20[0-9]{2})\b",          # سنوات
        r"\b\d{1,3}(?:[.,]\d{3})+\b",             # آلاف بفواصل
        r"\b\d+(?:[.,]\d+)?\b",
    ]
    found: list[str] = []
    for p in pats:
        for m in re.finditer(p, t):
            found.append(m.group(0))
    return found


def find_dates(text: str) -> list[str]:
    """تواريخ ميلادية (أرقام أو أسماء شهور عربية/إنجليزية) + سنوات مجرّدة."""
    t = latin_digits(text)
    months = (
        "يناير|فبراير|مارس|أبريل|ابريل|مايو|يونيو|يوليو|أغسطس|اغسطس|سبتمبر|أكتوبر|اكتوبر|نوفمبر|ديسمبر|"
        "January|February|March|April|May|June|July|August|September|October|November|December"
    )
    specific = [
        rf"\b\d{{1,2}}\s+(?:{months})\s+\d{{3,4}}\b",
        rf"\b(?:{months})\s+\d{{1,2}},?\s+\d{{3,4}}\b",
        r"\b\d{1,2}/\d{1,2}/\d{2,4}\b",
        r"\b(?:1[0-9]{3}|20[0-9]{2})\s?(?:ق\.?م|م|BC|AD|CE|BCE)\b",
    ]
    out: list[str] = []
    spans: list[tuple[int, int]] = []
    for p in specific:
        for m in re.finditer(p, t):
            out.append(m.group(0).strip())
            spans.append(m.span())
    # سنوات مجرّدة (1914... ) غير مغطاة بنمط أطول
    for m in re.finditer(r"\b(?:1[0-9]{3}|20[0-9]{2})\b", t):
        s, e = m.span()
        if any(s >= a and e <= b for a, b in spans):
            continue
        out.append(m.group(0))
    # بلا تكرار
    seen: set[str] = set()
    res: list[str] = []
    for d in out:
        k = normalize(d)
        if k and k not in seen:
            seen.add(k)
            res.append(d)
    return res


def find_quotes(text: str) -> list[str]:
    pats = [r"«([^»]{4,200})»", r"\"([^\"]{4,200})\"", r"“([^”]{4,200})”", r"'([^']{4,200})'"]
    out: list[str] = []
    for p in pats:
        out += [m.strip() for m in re.findall(p, text)]
    return out


STOPWORDS = set(
    """
في من على عن إلى الى مع هذا هذه ذلك التي الذي الذين كان كانت يكون تكون لم لن لا ما هو هي هم أن ان إن أو او ثم قد كل بعض غير بين بعد قبل عند عندما حيث كما لكن حتى إذا اذا لأن لان وهو وهي به بها له لها منه منها عليه عليها التي وهو
the a an of in on at to for with and or but is are was were be been this that these those it its as by from not no yes
""".split()
)


def keywords(text: str, top: int = 30) -> list[tuple[str, int]]:
    """كلمات مهمة (ترددًا) بلا وقفيات."""
    freq: dict[str, int] = {}
    for w in words(text):
        n = normalize(w).lower()
        if len(n) < 3 or n in STOPWORDS:
            continue
        freq[n] = freq.get(n, 0) + 1
    return sorted(freq.items(), key=lambda kv: -kv[1])[:top]
