"""Replaceable discovery providers.

The architecture deliberately avoids scraping one search engine's HTML as the
permanent core.  Providers return structured candidates; the workflow decides
which links to read.
"""
from __future__ import annotations

from typing import Any, Protocol

from .http import HttpClient


class DiscoveryProvider(Protocol):
    name: str

    def available(self) -> bool: ...

    def search(self, query: str, *, limit: int = 8) -> list[dict[str, Any]]: ...


class WikipediaDiscovery:
    name = "wikipedia"

    def __init__(self, client: HttpClient, langs: tuple[str, ...] = ("ar", "en")):
        self.client = client
        self.langs = langs

    def available(self) -> bool:
        return True

    def search(self, query: str, *, limit: int = 8) -> list[dict[str, Any]]:
        out = []
        for lang in self.langs:
            try:
                data = self.client.get_json(
                    f"https://{lang}.wikipedia.org/w/api.php",
                    {"action": "query", "list": "search", "srsearch": query, "srlimit": limit, "format": "json"},
                )
            except Exception:
                continue
            for hit in data.get("query", {}).get("search", []) or []:
                out.append(
                    {
                        "provider": self.name,
                        "language": lang,
                        "title": hit.get("title", ""),
                        "url": f"https://{lang}.wikipedia.org/wiki/{hit.get('title', '').replace(' ', '_')}",
                        "snippet": hit.get("snippet", ""),
                    }
                )
        return out[:limit]


class WikidataDiscovery:
    name = "wikidata"

    def __init__(self, client: HttpClient):
        self.client = client

    def available(self) -> bool:
        return True

    def search(self, query: str, *, limit: int = 8) -> list[dict[str, Any]]:
        try:
            data = self.client.get_json(
                "https://www.wikidata.org/w/api.php",
                {"action": "wbsearchentities", "search": query, "language": "en", "limit": limit, "format": "json", "type": "item"},
            )
        except Exception:
            return []
        out = []
        for hit in data.get("search", []) or []:
            out.append(
                {
                    "provider": self.name,
                    "title": hit.get("label", ""),
                    "url": hit.get("concepturi", ""),
                    "snippet": hit.get("description", ""),
                    "qid": hit.get("id"),
                }
            )
        return out


class CommonsDiscovery:
    name = "wikimedia_commons"

    def __init__(self, client: HttpClient):
        self.client = client

    def available(self) -> bool:
        return True

    def search(self, query: str, *, limit: int = 8) -> list[dict[str, Any]]:
        try:
            data = self.client.get_json(
                "https://commons.wikimedia.org/w/api.php",
                {"action": "query", "list": "search", "srsearch": query, "srnamespace": 6, "srlimit": limit, "format": "json"},
            )
        except Exception:
            return []
        out = []
        for hit in data.get("query", {}).get("search", []) or []:
            title = hit.get("title", "")
            out.append(
                {
                    "provider": self.name,
                    "title": title,
                    "url": f"https://commons.wikimedia.org/wiki/{title.replace(' ', '_')}",
                    "snippet": hit.get("snippet", ""),
                }
            )
        return out


class LocalLibraryDiscovery:
    name = "local_icon_library"

    def __init__(self):
        self._available = None

    def available(self) -> bool:
        if self._available is None:
            try:
                from .local_library import build_index

                build_index()
                self._available = True
            except Exception:
                self._available = False
        return bool(self._available)

    def search(self, query: str, *, limit: int = 8) -> list[dict[str, Any]]:
        if not self.available():
            return []
        try:
            from .local_library import search_icons

            icons = search_icons([query], limit=limit)
        except Exception:
            return []
        return [{"provider": self.name, "title": i.get("name", ""), "url": i.get("file", ""), "local": True} for i in icons]


class NullDiscoveryProvider:
    name = "none"

    def available(self) -> bool:
        return False

    def search(self, query: str, *, limit: int = 8) -> list[dict[str, Any]]:
        return []


class DiscoveryRegistry:
    def __init__(self, providers: list[DiscoveryProvider] | None = None):
        self.providers = providers or []

    def available(self) -> list[str]:
        return [p.name for p in self.providers if p.available()]

    def search_all(self, query: str, *, limit: int = 8) -> list[dict[str, Any]]:
        results = []
        for provider in self.providers:
            if not provider.available():
                continue
            try:
                results.extend(provider.search(query, limit=limit))
            except Exception:
                continue
        return results
