"""ويكيميديا كومنز: البحث عن ملفات + بياناتها + رخصتها."""
from __future__ import annotations

from urllib.parse import quote

from ..core.util import strip_html
from .http import HttpClient, RateLimited

COMMONS_API = "https://commons.wikimedia.org/w/api.php"
FILE_PATH = "https://commons.wikimedia.org/wiki/Special:FilePath/"


class Commons:
    def __init__(self, client: HttpClient):
        self.c = client

    def search_files(self, query: str, *, limit: int = 10, lang: str = "en") -> list[str]:
        """بحث في نطاق الملفات (6) — يعيد عناوين مثل File:X.jpg."""
        try:
            data = self.c.get_json(
                COMMONS_API,
                {
                    "action": "query",
                    "list": "search",
                    "srsearch": query,
                    "srnamespace": 6,
                    "srlimit": limit,
                    "format": "json",
                },
            )
        except RateLimited:
            raise
        except Exception:
            return []
        return [h["title"] for h in data.get("query", {}).get("search", [])]

    def file_info(self, titles: list[str], *, thumb_width: int = 1600) -> list[dict]:
        if not titles:
            return []
        out: list[dict] = []
        for chunk_start in range(0, len(titles), 20):
            chunk = titles[chunk_start : chunk_start + 20]
            try:
                data = self.c.get_json(
                    COMMONS_API,
                    {
                        "action": "query",
                        "titles": "|".join(chunk),
                        "prop": "imageinfo",
                        "iiprop": "url|size|mime|extmetadata|user",
                        "iiurlwidth": thumb_width,
                        "format": "json",
                    },
                )
            except RateLimited:
                raise
            except Exception:
                continue
            pages = data.get("query", {}).get("pages", {})
            for page in pages.values():
                infos = page.get("imageinfo") or []
                if not infos:
                    continue
                info = infos[0]
                ext = info.get("extmetadata", {}) or {}

                def meta(key: str) -> str:
                    v = ext.get(key, {})
                    return strip_html(v.get("value")) if isinstance(v, dict) else ""

                mime = info.get("mime") or ""
                is_vector = "svg" in mime.lower()
                license_name = meta("LicenseShortName") or meta("UsageTerms") or meta("License")
                out.append(
                    {
                        "title": page.get("title", ""),
                        "page_url": info.get("descriptionurl") or f"https://commons.wikimedia.org/wiki/{quote(page.get('title', ''))}",
                        "url": info.get("url") if is_vector else (info.get("thumburl") or info.get("url")),
                        "original_url": info.get("url"),
                        "thumb_url": info.get("thumburl") or info.get("url"),
                        "width": info.get("width"),
                        "height": info.get("height"),
                        "mime": mime,
                        "is_vector": is_vector,
                        "size": info.get("size"),
                        "license": license_name,
                        "license_url": meta("LicenseUrl"),
                        "copyrighted": meta("Copyrighted"),
                        "attribution_required": meta("AttributionRequired"),
                        "artist": meta("Artist"),
                        "credit": meta("Credit"),
                        "permission": meta("Permission")[:200],
                        "description": meta("ImageDescription")[:400],
                        "date": meta("DateTimeOriginal"),
                        "uploader": info.get("user", ""),
                    }
                )
        return out

    def find_images(self, query: str, *, limit: int = 8, thumb_width: int = 1600) -> list[dict]:
        titles = self.search_files(query, limit=limit)
        return self.file_info(titles, thumb_width=thumb_width)

    @staticmethod
    def file_url(filename: str, width: int | None = None) -> str:
        url = FILE_PATH + quote(filename.replace(" ", "_"))
        if width:
            url += f"?width={width}"
        return url


COMMONS_API = "https://commons.wikimedia.org/w/api.php"
FILE_PATH = "https://commons.wikimedia.org/wiki/Special:FilePath/"


class Commons:
    def __init__(self, client: HttpClient):
        self.c = client

    def search_files(self, query: str, *, limit: int = 10, lang: str = "en") -> list[str]:
        """بحث في نطاق الملفات (6) — يعيد عناوين مثل File:X.jpg."""
        try:
            data = self.c.get_json(
                COMMONS_API,
                {
                    "action": "query",
                    "list": "search",
                    "srsearch": query,
                    "srnamespace": 6,
                    "srlimit": limit,
                    "format": "json",
                },
            )
        except RateLimited:
            raise
        except Exception:
            return []
        return [h["title"] for h in data.get("query", {}).get("search", [])]

    def file_info(self, titles: list[str], *, thumb_width: int = 1600) -> list[dict]:
        if not titles:
            return []
        out: list[dict] = []
        for chunk_start in range(0, len(titles), 20):
            chunk = titles[chunk_start : chunk_start + 20]
            try:
                data = self.c.get_json(
                    COMMONS_API,
                    {
                        "action": "query",
                        "titles": "|".join(chunk),
                        "prop": "imageinfo",
                        "iiprop": "url|size|mime|extmetadata|user",
                        "iiurlwidth": thumb_width,
                        "format": "json",
                    },
                )
            except RateLimited:
                raise
            except Exception:
                continue
            pages = data.get("query", {}).get("pages", {})
            for page in pages.values():
                infos = page.get("imageinfo") or []
                if not infos:
                    continue
                info = infos[0]
                ext = info.get("extmetadata", {}) or {}

                def meta(key: str) -> str:
                    v = ext.get(key, {})
                    return strip_html(v.get("value")) if isinstance(v, dict) else ""

                mime = info.get("mime") or ""
                is_vector = "svg" in mime.lower()
                license_name = meta("LicenseShortName") or meta("UsageTerms") or meta("License")
                out.append(
                    {
                        "title": page.get("title", ""),
                        "page_url": info.get("descriptionurl") or f"https://commons.wikimedia.org/wiki/{quote(page.get('title', ''))}",
                        "url": info.get("url") if is_vector else (info.get("thumburl") or info.get("url")),
                        "original_url": info.get("url"),
                        "thumb_url": info.get("thumburl") or info.get("url"),
                        "width": info.get("width"),
                        "height": info.get("height"),
                        "mime": mime,
                        "is_vector": is_vector,
                        "size": info.get("size"),
                        "license": license_name,
                        "license_url": meta("LicenseUrl"),
                        "copyrighted": meta("Copyrighted"),
                        "attribution_required": meta("AttributionRequired"),
                        "artist": meta("Artist"),
                        "credit": meta("Credit"),
                        "permission": meta("Permission")[:200],
                        "description": meta("ImageDescription")[:400],
                        "date": meta("DateTimeOriginal"),
                        "uploader": info.get("user", ""),
                    }
                )
        return out

    def find_images(self, query: str, *, limit: int = 8, thumb_width: int = 1600) -> list[dict]:
        titles = self.search_files(query, limit=limit)
        return self.file_info(titles, thumb_width=thumb_width)

    @staticmethod
    def file_url(filename: str, width: int | None = None) -> str:
        url = FILE_PATH + quote(filename.replace(" ", "_"))
        if width:
            url += f"?width={width}"
        return url
