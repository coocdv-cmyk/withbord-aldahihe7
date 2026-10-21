"""ويكيبيديا: ملخصات وسياق للتحقق (بلا نسخ — للفهم فقط)."""
from __future__ import annotations

from urllib.parse import quote

from .http import HttpClient, RateLimited


class Wikipedia:
    def __init__(self, client: HttpClient):
        self.c = client

    def summary(self, title: str, lang: str = "ar") -> dict | None:
        url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{quote(title)}"
        try:
            data = self.c.get_json(url, ttl=7 * 86400)
        except RateLimited:
            raise
        except Exception:
            return None
        if data.get("type", "").endswith("not_found"):
            return None
        return {
            "title": data.get("title"),
            "extract": data.get("extract", ""),
            "description": data.get("description", ""),
            "url": (data.get("content_urls", {}).get("desktop", {}) or {}).get("page"),
            "thumbnail": (data.get("thumbnail", {}) or {}).get("source"),
        }

    def search(self, query: str, lang: str = "ar", limit: int = 5) -> list[dict]:
        url = f"https://{lang}.wikipedia.org/w/api.php"
        try:
            data = self.c.get_json(
                url,
                {"action": "query", "list": "search", "srsearch": query, "srlimit": limit, "format": "json"},
            )
        except RateLimited:
            raise
        except Exception:
            return []
        return [
            {"title": h["title"], "snippet": h.get("snippet", "")[:220], "wordcount": h.get("wordcount", 0)}
            for h in data.get("query", {}).get("search", [])
        ]

    def best_summary(self, query: str, langs=("ar", "en"), *, avoid: list[str] | None = None) -> dict | None:
        """أفضل ملخص لمقالة مطابقة (مع استبعاد كلمات مثل «اغتيال/معركة» عند البحث عن شخص)."""
        avoid = avoid or []
        for lang in langs:
            hits = self.search(query, lang=lang, limit=4)
            for h in hits[:3]:
                title = h.get("title") or ""
                if any(a in title for a in avoid):
                    continue
                s = self.summary(title, lang=lang)
                if s and s.get("extract"):
                    s["lang"] = lang
                    return s
        return None



class Wikipedia:
    def __init__(self, client: HttpClient):
        self.c = client

    def summary(self, title: str, lang: str = "ar") -> dict | None:
        url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{quote(title)}"
        try:
            data = self.c.get_json(url, ttl=7 * 86400)
        except RateLimited:
            raise
        except Exception:
            return None
        if data.get("type", "").endswith("not_found"):
            return None
        return {
            "title": data.get("title"),
            "extract": data.get("extract", ""),
            "description": data.get("description", ""),
            "url": (data.get("content_urls", {}).get("desktop", {}) or {}).get("page"),
            "thumbnail": (data.get("thumbnail", {}) or {}).get("source"),
        }

    def search(self, query: str, lang: str = "ar", limit: int = 5) -> list[dict]:
        url = f"https://{lang}.wikipedia.org/w/api.php"
        try:
            data = self.c.get_json(
                url,
                {"action": "query", "list": "search", "srsearch": query, "srlimit": limit, "format": "json"},
            )
        except RateLimited:
            raise
        except Exception:
            return []
        return [
            {"title": h["title"], "snippet": h.get("snippet", "")[:220], "wordcount": h.get("wordcount", 0)}
            for h in data.get("query", {}).get("search", [])
        ]

    def best_summary(self, query: str, langs=("ar", "en"), *, avoid: list[str] | None = None) -> dict | None:
        """أفضل ملخص لمقالة مطابقة (مع استبعاد كلمات مثل «اغتيال/معركة» عند البحث عن شخص)."""
        avoid = avoid or []
        for lang in langs:
            hits = self.search(query, lang=lang, limit=4)
            for h in hits[:3]:
                title = h.get("title") or ""
                if any(a in title for a in avoid):
                    continue
                s = self.summary(title, lang=lang)
                if s and s.get("extract"):
                    s["lang"] = lang
                    return s
        return None
