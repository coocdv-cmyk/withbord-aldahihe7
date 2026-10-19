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


class HttpClient:
    def __init__(self, user_agent: str, *, timeout: int = 45, cache: bool = True):
        self.ua = user_agent
        self.timeout = timeout
        self.cache = cache
        self.session = requests.Session()
        retry = Retry(total=3, backoff_factor=0.6, status_forcelist=(429, 500, 502, 503, 504), allowed_methods=("GET", "POST"))
        adapter = HTTPAdapter(max_retries=retry, pool_connections=8, pool_maxsize=16)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.session.headers.update({"User-Agent": user_agent, "Accept-Language": "ar,en;q=0.8"})

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
        r = self.session.get(url, params=params, timeout=self.timeout, headers=headers)
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
        r = self.session.post(url, data=data, timeout=self.timeout, headers=headers)
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
        r = self.session.get(url, timeout=self.timeout, headers=headers, stream=True)
        r.raise_for_status()
        buf = r.content
        if self.cache and len(buf) < 60_000_000:
            self._write_cache(key, buf, binary=True)
        return buf

    def head_ok(self, url: str, *, timeout: int = 8) -> bool:
        try:
            r = self.session.head(url, timeout=timeout, allow_redirects=True)
            return r.status_code < 400
        except Exception:
            return False
