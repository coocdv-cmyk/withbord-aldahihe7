"""Safe URL handling and bounded HTTP fetching for research.

Web pages and documents are treated as untrusted data.  This module validates
URL completeness, blocks local/private targets, enforces byte limits and records
access level instead of pretending that every response is full text.
"""
from __future__ import annotations

import ipaddress
import socket
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import requests

from .evidence import AccessLevel, SourceAccess


INCOMPLETE_MARKERS = ("...", "…", "<", ">", " ", "undefined", "null", "example.com/...")


def normalise_url(url: str) -> str:
    return (url or "").strip()


def is_complete_url(url: str) -> bool:
    value = normalise_url(url)
    if not value or any(marker in value for marker in INCOMPLETE_MARKERS):
        return False
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc) and "." in parsed.netloc


def _resolve_addresses(hostname: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(hostname, None)
    except Exception:
        return []
    out = []
    for info in infos:
        addr = info[4][0]
        if addr not in out:
            out.append(addr)
    return out


def _is_private_address(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return True
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def is_safe_url(url: str, *, allow_hosts: set[str] | None = None) -> tuple[bool, str]:
    if not is_complete_url(url):
        return False, "incomplete or invalid URL"
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if not host:
        return False, "missing host"
    if host.lower() in {"localhost", "127.0.0.1", "::1"}:
        return False, "localhost is not allowed"
    if allow_hosts and host.lower() not in {h.lower() for h in allow_hosts}:
        return False, "host not in allow list"
    addresses = _resolve_addresses(host)
    if not addresses:
        return False, "host did not resolve"
    if any(_is_private_address(addr) for addr in addresses):
        return False, "private or local network address"
    return True, "ok"


def classify_resource_type(url: str, content_type: str = "") -> str:
    low = (url + " " + content_type).lower()
    if "pdf" in low:
        return "pdf"
    if "epub" in low or low.endswith(".epub"):
        return "epub"
    if any(x in low for x in ("image/", ".jpg", ".jpeg", ".png", ".webp", ".svg", ".tif")):
        return "image"
    if "json" in low or "iiif" in low:
        return "json"
    if any(x in low for x in ("video/", ".mp4", ".webm")):
        return "video"
    if any(x in low for x in ("audio/", ".mp3", ".wav")):
        return "audio"
    if "html" in low or "text/" in low:
        return "html"
    return "unknown"


def fetch_url(url: str, *, timeout: int = 20, max_bytes: int = 5_000_000,
              user_agent: str = "rasm-pro research (local)", headers: dict[str, str] | None = None) -> tuple[SourceAccess, bytes]:
    safe, reason = is_safe_url(url)
    access = SourceAccess(url=url, normalized_url=normalise_url(url), complete=is_complete_url(url),
                          retrieved_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    if not safe:
        access.access_level = AccessLevel.UNAVAILABLE.value
        access.error = reason
        return access, b""

    session = requests.Session()
    session.headers.update({"User-Agent": user_agent, "Accept-Language": "ar,en;q=0.8"})
    if headers:
        session.headers.update(headers)

    try:
        response = session.get(url, timeout=timeout, stream=True, allow_redirects=True)
    except requests.RequestException as exc:
        access.access_level = AccessLevel.UNAVAILABLE.value
        access.error = f"request failed: {exc}"
        return access, b""

    final_url = response.url or url
    safe_final, final_reason = is_safe_url(final_url)
    if not safe_final:
        response.close()
        access.access_level = AccessLevel.UNAVAILABLE.value
        access.error = f"redirect target rejected: {final_reason}"
        return access, b""

    try:
        chunks = []
        total = 0
        for chunk in response.iter_content(chunk_size=65536):
            if not chunk:
                continue
            total += len(chunk)
            if total > max_bytes:
                chunks.append(chunk[: max(0, max_bytes - (total - len(chunk)))])
                total = max_bytes + 1
                break
            chunks.append(chunk)
        data = b"".join(chunks)
    except requests.RequestException as exc:
        response.close()
        access.access_level = AccessLevel.UNAVAILABLE.value
        access.error = f"read failed: {exc}"
        return access, b""
    finally:
        response.close()

    access.normalized_url = final_url
    access.byte_size = len(data)
    access.content_hash = _sha256(data)
    access.resource_type = classify_resource_type(final_url, response.headers.get("Content-Type", ""))
    if response.status_code >= 400:
        access.access_level = AccessLevel.UNAVAILABLE.value
        access.error = f"HTTP {response.status_code}"
        return access, data
    if len(data) > max_bytes:
        access.access_level = AccessLevel.PREVIEW.value
        access.notes.append("response truncated by byte limit")
    else:
        access.access_level = AccessLevel.FULL_TEXT.value if access.resource_type in {"html", "text", "json", "pdf", "epub"} else AccessLevel.METADATA_ONLY.value
    access.title = response.headers.get("Content-Disposition", "")[:120]
    return access, data


def _sha256(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()
