"""ويكي بيانات (Wikidata): بحث الكيانات + الحقائق + الوسائط المرتبطة."""
from __future__ import annotations

import re
from urllib.parse import quote

from ..core import arabic
from ..core.util import strip_html
from .http import HttpClient

WD_API = "https://www.wikidata.org/w/api.php"
SPARQL = "https://query.wikidata.org/sparql"
COMMONS_FILE = "https://commons.wikimedia.org/wiki/Special:FilePath/"


def _parse_time(value: str) -> str | None:
    """+1914-07-28T00:00:00Z → 1914-07-28"""
    if not value:
        return None
    v = value.lstrip("+")
    return v.split("T")[0]


class Wikidata:
    def __init__(self, client: HttpClient):
        self.c = client

    # ---------- بحث ----------
    def search_entity(self, label: str, lang: str = "ar", limit: int = 5) -> list[dict]:
        data = self.c.get_json(
            WD_API,
            {
                "action": "wbsearchentities",
                "search": label,
                "language": lang,
                "uselang": lang,
                "format": "json",
                "limit": limit,
                "type": "item",
            },
        )
        out = []
        for hit in data.get("search", []):
            out.append(
                {
                    "qid": hit.get("id"),
                    "label": hit.get("label"),
                    "description": hit.get("description", ""),
                    "url": hit.get("concepturi"),
                }
            )
        return out

    def search_entity_multi(self, label: str, langs=("ar", "en"), limit: int = 4) -> list[dict]:
        seen: dict[str, dict] = {}
        for lang in langs:
            try:
                for h in self.search_entity(label, lang, limit=limit):
                    if h["qid"] and h["qid"] not in seen:
                        seen[h["qid"]] = h
            except Exception:
                continue
        return list(seen.values())

    # ---------- حقائق ----------
    def get_entities(self, qids: list[str], langs=("ar", "en")) -> dict:
        if not qids:
            return {}
        data = self.c.get_json(
            WD_API,
            {
                "action": "wbgetentities",
                "ids": "|".join(qids[:40]),
                "props": "labels|descriptions|claims|sitelinks",
                "languages": "|".join(langs),
                "format": "json",
            },
        )
        return data.get("entities", {})

    @staticmethod
    def _claim_values(entity: dict, prop: str) -> list:
        out = []
        for snak in entity.get("claims", {}).get(prop, []) or []:
            dv = snak.get("mainsnak", {}).get("datavalue")
            if dv:
                out.append(dv.get("value"))
        return out

    @staticmethod
    def _label(entity: dict, langs=("ar", "en")) -> str:
        labels = entity.get("labels", {})
        for l in langs:
            if l in labels:
                return labels[l]["value"]
        return next((v["value"] for v in labels.values()), "")

    def by_sitelink(self, lang: str, title: str) -> str | None:
        """عنوان مقالة ويكيبيديا → QID."""
        try:
            data = self.c.get_json(
                WD_API,
                {"action": "wbgetentities", "sites": f"{lang}wiki", "titles": title, "props": "info", "format": "json"},
            )
        except Exception:
            return None
        for qid, ent in (data.get("entities") or {}).items():
            if qid.startswith("Q") and "missing" not in ent:
                return qid
        return None

    @staticmethod
    def _description(entity: dict, langs=("ar", "en")) -> str:
        descs = entity.get("descriptions", {})
        for l in langs:
            if l in descs:
                return descs[l]["value"]
        return next((v["value"] for v in descs.values()), "")

    def facts(self, qid: str) -> dict | None:
        data = self.get_entities([qid])
        ent = data.get(qid)
        if not ent or "missing" in ent:
            return None
        V = self._claim_values

        def first(prop):
            vals = V(ent, prop)
            return vals[0] if vals else None

        def qid_list(prop):
            out = []
            for v in V(ent, prop):
                if isinstance(v, dict) and "id" in v:
                    out.append(v["id"])
            return out

        def time_of(prop):
            t = first(prop)
            if isinstance(t, dict):
                return _parse_time(t.get("time"))
            return None

        facts = {
            "qid": qid,
            "label": self._label(ent),
            "label_en": (ent.get("labels", {}).get("en", {}) or {}).get("value", ""),
            "description": self._description(ent),
            "instance_of": qid_list("P31"),
            "image": first("P18"),
            "flag": first("P41"),
            "coat": first("P94"),
            "locator_map": first("P242"),
            "coords": (lambda c: [c.get("latitude"), c.get("longitude")] if isinstance(c, dict) else None)(first("P625")),
            "inception": time_of("P571"),
            "point_in_time": time_of("P585"),
            "dissolved": time_of("P576"),
            "start": time_of("P580"),
            "end": time_of("P582"),
            "birth": time_of("P569"),
            "death": time_of("P570"),
            "country": qid_list("P17"),
            "capital": qid_list("P36"),
            "population": (lambda v: v.get("amount") if isinstance(v, dict) else None)(first("P1082")),
            "iso2": first("P297"),
            "occupation": qid_list("P106"),
            "sitelinks": {k: v.get("title") for k, v in (ent.get("sitelinks") or {}).items() if k.endswith("wiki")},
        }
        # رابط صورة/علم/خريطة عبر Commons
        for key in ("image", "flag", "coat", "locator_map"):
            if facts.get(key):
                facts[key + "_url"] = COMMONS_FILE + quote(str(facts[key]).replace(" ", "_"))
        return facts

    @staticmethod
    def _year_of(value) -> int | None:
        if not value:
            return None
        m = re.search(r"(-?\d{3,4})", str(value))
        if not m:
            return None
        y = abs(int(m.group(1)))
        return y if 800 <= y <= 2100 else None

    def facts_years(self, facts: dict) -> list[int]:
        years = []
        for k in ("inception", "point_in_time", "start", "end", "birth", "death", "dissolved"):
            y = self._year_of(facts.get(k))
            if y:
                years.append(y)
        return years

    def life_span(self, facts: dict) -> tuple[int | None, int | None]:
        """(بداية، نهاية) — للتحقق الزمني: هل الكيان موجود في سنة معيّنة؟"""
        start = None
        end = None
        for k in ("inception", "start", "birth"):
            start = start or self._year_of(facts.get(k))
        for k in ("end", "dissolved", "death"):
            end = end or self._year_of(facts.get(k))
        return start, end

    def era_score(self, facts: dict, years: list[int]) -> float:
        """قوة دليل أن الكيان يخص سنوات السكريبت: مطابقة صريحة > احتواء مغلق > بداية قريبة."""
        if not years or not facts:
            return 0.0
        f_years = self.facts_years(facts)
        if any(y in f_years for y in years):
            return 4.0
        start, end = self.life_span(facts)
        if start is None:
            return 0.0
        if end is not None:
            return 3.0 if any(start <= y <= end for y in years) else 0.0
        # بلا نهاية: معاصر فقط إذا بدأ قبل السنة بقليل (وإلا فنحن أمام كيان قديم منتهٍ فعلًا)
        return 2.0 if any(0 <= (y - start) <= 40 for y in years) else 0.0

    def resolve(
        self,
        name: str,
        *,
        lang_pref=("ar", "en"),
        context: str = "",
        dates: list[str] | None = None,
        expected_types: list[str] | None = None,
        search_names: list[str] | None = None,
    ) -> dict | None:
        """اسم (+سياق/تواريخ) → أفضل كيان مع تبرير الاختيار.

        يحل مشكلة الالتباس التاريخي: «معاهدة فرساي» في سياق 1919 ≠ نسخة 1757.
        """
        hits: list[dict] = []
        seen: set[str] = set()
        for n in (search_names or [name]):
            for h in self.search_entity_multi(n, langs=lang_pref):
                if h["qid"] and h["qid"] not in seen:
                    seen.add(h["qid"])
                    hits.append(h)
        if not hits:
            return None

        wanted_years = [self._year_of(d) for d in (dates or [])]
        wanted_years = [y for y in wanted_years if y]
        ctx_words = [w for w in arabic.normalize(context).split() if len(w) > 3][:14]

        scored: list[tuple[float, dict]] = []
        for i, h in enumerate(hits[:6]):
            f = self.facts(h["qid"])
            if not f or not f.get("label"):
                continue
            desc = f"{f.get('description') or ''} {h.get('description') or ''}"
            score = 0.0
            for y in wanted_years:
                if str(y) in desc:
                    score += 2
            # الدليل الزمني (مطابقة صريحة > احتواء مغلق > بداية قريبة)
            score += self.era_score(f, wanted_years)
            if expected_types:
                inst = f.get("instance_of") or []
                if any(t in inst for t in expected_types):
                    score += 5
            for w in ctx_words:
                if w in desc:
                    score += 1
            if f.get("image"):
                score += 1.5
            if f.get("iso2") or f.get("flag"):
                score += 0.5
            if arabic.normalize(name) == arabic.normalize(h.get("label") or ""):
                score += 2
            score -= i * 0.15
            scored.append((score, f))

        if not scored:
            return None
        scored.sort(key=lambda t: -t[0])
        best = dict(scored[0][1])
        best["match_score"] = round(scored[0][0], 2)
        best["candidates"] = [
            {"qid": f.get("qid"), "label": f.get("label"), "description": f.get("description"), "score": round(s, 2)}
            for s, f in scored[:4]
        ]
        return best

    # ---------- SPARQL ----------
    def sparql(self, query: str, *, ttl: int = 3600) -> list[dict]:
        data = self.c.get_json(
            SPARQL,
            {"query": query, "format": "json"},
            ttl=ttl,
            headers={"Accept": "application/sparql-results+json"},
        )
        rows = data.get("results", {}).get("bindings", [])
        out = []
        for r in rows:
            out.append({k: v.get("value") for k, v in r.items()})
        return out
