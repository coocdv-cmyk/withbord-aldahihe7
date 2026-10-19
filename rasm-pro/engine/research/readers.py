"""Document readers for research.

Readers preserve the original text alongside a normalised form.  OCR and model
summaries are never treated as verbatim quotations automatically.
"""
from __future__ import annotations

import html
import io
import json
import re
import zipfile
from typing import Any

from .evidence import AccessLevel
from .urls import classify_resource_type


class _HTMLTextExtractor:
    def __init__(self) -> None:
        self.parts: list[str] = []
        self.links: list[str] = []
        self.title = ""
        self._skip = 0
        self._current_tag = ""

    def feed(self, data: str) -> None:
        from html.parser import HTMLParser

        class Parser(HTMLParser):
            pass

        # Use a closure-based parser to keep the implementation compact.
        parser = _HTMLParser(self)
        parser.feed(data)

    def text(self) -> str:
        return "\n".join(p for p in self.parts if p.strip())


class _HTMLParser:
    def __init__(self, owner: _HTMLTextExtractor):
        self.owner = owner
        from html.parser import HTMLParser

        class P(HTMLParser):
            def __init__(self, o):
                super().__init__(convert_charrefs=True)
                self.o = o

            def handle_starttag(self, tag, attrs):
                if tag in {"script", "style", "noscript"}:
                    self.o._skip += 1
                if tag == "a":
                    for k, v in attrs:
                        if k == "href" and v:
                            self.o.links.append(v)
                self.o._current_tag = tag

            def handle_endtag(self, tag):
                if tag in {"script", "style", "noscript"} and self.o._skip:
                    self.o._skip -= 1
                if tag in {"p", "div", "li", "h1", "h2", "h3", "h4", "section", "article", "br"}:
                    self.o.parts.append("")

            def handle_data(self, data):
                if self.o._skip:
                    return
                value = data.strip()
                if value:
                    self.o.parts.append(value)

        self.parser = P(owner)

    def feed(self, data: str) -> None:
        self.parser.feed(data)


def extract_html(data: bytes, url: str = "") -> dict[str, Any]:
    text_data = data.decode("utf-8", errors="replace")
    extractor = _HTMLTextExtractor()
    extractor.feed(text_data)
    title_match = re.search(r"<title[^>]*>(.*?)</title>", text_data, re.I | re.S)
    title = html.unescape(title_match.group(1).strip()) if title_match else ""
    body = extractor.text()
    # Collapse excessive blank lines.
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    return {
        "reader": "html",
        "title": title,
        "text": body,
        "original_text": body,
        "normalised_text": _normalise_text(body),
        "links": extractor.links[:200],
        "page_count": 1,
    }


def _normalise_text(text: str) -> str:
    text = html.unescape(text or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _try_import(name: str):
    try:
        module = __import__(name)
        return module
    except Exception:
        return None


def extract_pdf(data: bytes) -> dict[str, Any]:
    pypdf = _try_import("pypdf")
    if pypdf is not None:
        try:
            reader = pypdf.PdfReader(io.BytesIO(data))
            pages = []
            for i, page in enumerate(reader.pages, 1):
                try:
                    pages.append((i, page.extract_text() or ""))
                except Exception:
                    pages.append((i, ""))
            text = "\n\n".join(f"[page {i}]\n{t}" for i, t in pages)
            return {
                "reader": "pypdf",
                "title": "",
                "text": text,
                "original_text": text,
                "normalised_text": _normalise_text(text),
                "page_texts": [{"page": i, "text": t} for i, t in pages],
                "page_count": len(pages),
            }
        except Exception as exc:
            return {"reader": "pypdf", "error": str(exc), "text": "", "original_text": "", "normalised_text": "", "page_count": 0}

    pymupdf = _try_import("pymupdf")
    if pymupdf is not None:
        try:
            doc = pymupdf.open(stream=data, filetype="pdf")
            pages = []
            for i, page in enumerate(doc, 1):
                pages.append((i, page.get_text() or ""))
            text = "\n\n".join(f"[page {i}]\n{t}" for i, t in pages)
            return {
                "reader": "pymupdf",
                "title": doc.metadata.get("title", "") if hasattr(doc, "metadata") else "",
                "text": text,
                "original_text": text,
                "normalised_text": _normalise_text(text),
                "page_texts": [{"page": i, "text": t} for i, t in pages],
                "page_count": len(pages),
            }
        except Exception as exc:
            return {"reader": "pymupdf", "error": str(exc), "text": "", "original_text": "", "normalised_text": "", "page_count": 0}

    return {
        "reader": "unavailable",
        "error": "No PDF reader installed (optional: pypdf or pymupdf)",
        "text": "",
        "original_text": "",
        "normalised_text": "",
        "page_count": 0,
    }


def extract_epub(data: bytes) -> dict[str, Any]:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except Exception as exc:
        return {"reader": "epub", "error": str(exc), "text": "", "original_text": "", "normalised_text": "", "page_count": 0}

    html_items = [n for n in zf.namelist() if n.lower().endswith((".html", ".xhtml", ".htm"))]
    parts = []
    for name in sorted(html_items):
        try:
            raw = zf.read(name)
            parsed = extract_html(raw, "")
            if parsed.get("text"):
                parts.append(f"[{name}]\n{parsed['text']}")
        except Exception:
            continue
    text = "\n\n".join(parts)
    return {
        "reader": "epub",
        "text": text,
        "original_text": text,
        "normalised_text": _normalise_text(text),
        "page_count": len(html_items),
        "items": html_items,
    }


def extract_iiif_manifest(data: bytes) -> dict[str, Any]:
    try:
        manifest = json.loads(data.decode("utf-8", errors="replace"))
    except Exception as exc:
        return {"reader": "iiif", "error": str(exc), "text": "", "original_text": "", "normalised_text": "", "page_count": 0}

    label = manifest.get("label")
    if isinstance(label, dict):
        label = next(iter(label.values()), [""])[0] if label else ""
    canvases = []
    items = manifest.get("items") or manifest.get("sequences", [{}])
    if isinstance(items, list) and items and isinstance(items[0], dict) and "canvases" in items[0]:
        canvases = items[0].get("canvases", [])
    elif isinstance(items, list):
        canvases = items

    descriptions = []
    image_urls = []
    for canvas in canvases:
        c_label = canvas.get("label")
        if isinstance(c_label, dict):
            c_label = next(iter(c_label.values()), [""])[0] if c_label else ""
        descriptions.append(str(c_label or ""))
        for ann_page in canvas.get("items", []) or []:
            for ann in ann_page.get("items", []) or []:
                body = ann.get("body", {})
                if isinstance(body, dict) and body.get("id"):
                    image_urls.append(body["id"])
                elif isinstance(body, list):
                    for b in body:
                        if isinstance(b, dict) and b.get("id"):
                            image_urls.append(b["id"])

    text = "\n".join(x for x in descriptions if x)
    return {
        "reader": "iiif",
        "manifest_version": manifest.get("@context") or manifest.get("context"),
        "label": label or "",
        "text": text,
        "original_text": text,
        "normalised_text": _normalise_text(text),
        "canvas_count": len(canvases),
        "image_urls": image_urls[:100],
        "page_count": len(canvases),
    }


def read_document(access: Any, data: bytes) -> dict[str, Any]:
    resource_type = getattr(access, "resource_type", "") or ""
    url = getattr(access, "normalized_url", "") or getattr(access, "url", "")
    content_type = ""
    if resource_type == "pdf" or url.lower().endswith(".pdf"):
        result = extract_pdf(data)
    elif resource_type == "epub" or url.lower().endswith(".epub"):
        result = extract_epub(data)
    elif "iiif" in url.lower() or resource_type == "json":
        # Try IIIF first; fall back to HTML if it is not a manifest.
        try:
            parsed = json.loads(data.decode("utf-8", errors="replace"))
        except Exception:
            parsed = None
        if isinstance(parsed, dict) and ("@context" in parsed or "context" in parsed) and ("items" in parsed or "sequences" in parsed):
            result = extract_iiif_manifest(data)
        else:
            result = extract_html(data, url)
    else:
        result = extract_html(data, url)
    result.setdefault("url", url)
    result.setdefault("access_level", getattr(access, "access_level", ""))
    return result
