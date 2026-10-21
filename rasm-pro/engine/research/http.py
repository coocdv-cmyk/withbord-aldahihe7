"""عميل HTTP مع كاش على القرص + إعادة محاولة + مهلة محترمة."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ..core.paths import cache_file
from ..core.util import read_json, sha256_text, write_json


class RateLimited(RuntimeError):
    """The source asked us to slow down (HTTP 429)."""


class HttpClient:
    """HTTP with a disk cache, polite pacing, and a real backoff on 429.

    Wikimedia answers **429** when the caller asks faster than the etiquette
    allows.  The old retry (3 × 0.6 s) turned a rate limit into a failed
    research run: whole entities came back with *no* assets and nobody could
    tell the difference between "nothing found" and "we were throttled".
    Now:

    * requests to the same host are spaced by ``min_interval``;
    * a 429 waits 2 s → 8 s → 20 s (with jitter) before giving up;
    * the failure is raised as ``RateLimited`` so the caller can say so.
    """

    def __init__(
        self,
        user_agent: str,
        *,
        timeout: int = 45,
        cache: bool = True,
        min_interval: float = 0.35,
    ):
        self.ua = user_agent
        self.timeout = timeout
        self.cache = cache
        self.min_interval = max(0.0, float(min_interval))
        self._last_call: dict[str, float] = {}
        self.session = requests.Session()
        retry = Retry(
            total=3,
            backoff_factor=0.6,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET", "POST"),
            respect_retry_after_header=True,
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=8, pool_maxsize=16)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.session.headers.update({"User-Agent": user_agent, "Accept-Language": "ar,en;q=0.8"})

    # ---------- polite pacing ----------
    def _pace(self, url: str) -> None:
        """Space the calls to one host by ``min_interval``."""
        if not self.min_interval:
            return
        host = url.split("/")[2] if "://" in url else url
        last = self._last_call.get(host, 0.0)
        wait = self.min_interval - (time.time() - last)
        if wait > 0:
            time.sleep(wait)
        self._last_call[host] = time.time()

    def _request(self, method: str, url: str, *, params=None, data=None, headers=None, stream=False):
        """One paced request with a patient backoff on 429."""
        self._pace(url)
        for attempt, wait in enumerate((2.0, 8.0, 20.0)):
            response = self.session.request(
                method,
                url,
                params=params,
                data=data,
                headers=headers,
                timeout=self.timeout,
                stream=stream,
            )
            if response.status_code != 429:
                return response
            if attempt == 2:
                raise RateLimited(f"429 from {url} after three waits")
            time.sleep(wait + 0.4 * attempt)  # a little jitter, politely
        raise RateLimited(f"429 from {url}")

    # ---------- كاش ----------
    def _key(self, url: str, params: dict | None) -> str:
        return sha256_text(url + "|" + json.dumps(params or {}, sort_keys=True))[:32]

    def _read_cache(self, key: str, ttl: int | None, binary: bool):
        meta_p = cache_file("http", f"{key}.meta.json")
        data_p = cache_file("http", f"{key}.bin" if binary else f"{key}.json")
        if not (meta_p.exists() and data_p.exists()):
            return None
        meta = read_json(meta_p) or {}
        if ttl is not None and time.time() - float(meta.get("at", 0)) > ttl:
            return None
        if binary:
            return data_p.read_bytes()
        return read_json(data_p)

    def _write_cache(self, key: str, value, binary: bool):
        meta_p = cache_file("http", f"{key}.meta.json")
        write_json(meta_p, {"at": time.time()})
        if binary:
            cache_file("http", f"{key}.bin").write_bytes(value)
        else:
            write_json(cache_file("http", f"{key}.json"), value)

    # ---------- طلبات ----------
    def get_json(self, url: str, params: dict | None = None, *, ttl: int | None = 86400, headers: dict | None = None) -> Any:
        key = self._key(url, params)
        if self.cache:
            hit = self._read_cache(key, ttl, binary=False)
            if hit is not None:
                return hit
        r = self._request("GET", url, params=params, headers=headers)
        r.raise_for_status()
        data = r.json()
        if self.cache:
            self._write_cache(key, data, binary=False)
        return data

    def post_json(self, url: str, data: dict | None = None, *, headers: dict | None = None, ttl: int | None = 3600) -> Any:
        key = self._key(url, data)
        if self.cache:
            hit = self._read_cache(key, ttl, binary=False)
            if hit is not None:
                return hit
        r = self._request("POST", url, data=data, headers=headers)
        r.raise_for_status()
        out = r.json()
        if self.cache:
            self._write_cache(key, out, binary=False)
        return out

    def get_bytes(self, url: str, *, ttl: int | None = 7 * 86400, headers: dict | None = None) -> bytes:
        key = self._key(url, None)
        if self.cache:
            hit = self._read_cache(key, ttl, binary=True)
            if hit is not None:
                return hit
        r = self._request("GET", url, headers=headers, stream=True)
        r.raise_for_status()
        buf = r.content
        if self.cache and len(buf) < 60_000_000:
            self._write_cache(key, buf, binary=True)
        return buf

    def head_ok(self, url: str, *, timeout: int = 8) -> bool:
        try:
            self._pace(url)
            r = self.session.head(url, timeout=timeout, allow_redirects=True)
            return r.status_code < 400
        except Exception:
            return False
