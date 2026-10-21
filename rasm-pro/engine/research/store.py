"""مخزن الأصول: تنزيل + بصمة + تسجيل منشأ + ملف اعتمادات."""
from __future__ import annotations

import mimetypes
from datetime import datetime, timezone
from pathlib import Path

from ..core.log import get_logger
from ..core.util import read_json, sha256_bytes, sha256_file, slugify, write_json
from .http import HttpClient

log = get_logger("store")

EXT_BY_MIME = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/svg+xml": ".svg",
    "image/tiff": ".tif",
    "video/mp4": ".mp4",
    "audio/mpeg": ".mp3",
    "audio/wav": ".wav",
    "application/pdf": ".pdf",
}


def _ext_for(url: str, mime: str | None = None, kind: str = "image") -> str:
    if mime and mime in EXT_BY_MIME:
        return EXT_BY_MIME[mime]
    path = url.split("?")[0]
    for e in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg", ".tif", ".tiff", ".mp4", ".mp3", ".wav", ".pdf"):
        if path.lower().endswith(e):
            return ".jpg" if e == ".jpeg" else e
    guess = mimetypes.guess_extension(mime or "")
    if guess:
        return guess
    return ".bin"


class AssetStore:
    """يبقي كل أصل مستخدم مع بصمته ومنشئه ورخصته."""

    def __init__(self, project_dir: Path, client: HttpClient | None = None):
        self.root = Path(project_dir)
        self.client = client
        self.assets_dir = self.root / "assets"
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        self.registry_path = self.root / "research" / "assets.json"
        self.registry: list[dict] = read_json(self.registry_path, default=[]) or []
        self._by_sha = {r["sha256"]: r for r in self.registry if r.get("sha256")}

    # ---------- تنزيل ----------
    def download(self, url: str, *, kind: str = "image", subdir: str = "", mime: str | None = None,
                 record_meta: dict | None = None) -> dict | None:
        try:
            data = self.client.get_bytes(url)
        except Exception as e:
            log.warning("فشل تنزيل %s: %s", url[:120], e)
            return None
        if not data or len(data) < 64:
            return None
        sha = sha256_bytes(data)
        if sha in self._by_sha:
            existing = dict(self._by_sha[sha])
            existing["reused"] = True
            return existing

        ext = _ext_for(url, mime, kind)
        sub = slugify(subdir) if subdir else kind
        folder = self.assets_dir / sub
        folder.mkdir(parents=True, exist_ok=True)
        fname = f"{sha[:12]}{ext}"
        path = folder / fname
        path.write_bytes(data)

        rec = {
            "sha256": sha,
            "path": str(path.relative_to(self.root)).replace("\\", "/"),
            "bytes": len(data),
            "kind": kind,
            "mime": mime or mimetypes.guess_type(str(path))[0],
            "url": url,
            "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        rec.update(record_meta or {})
        self.registry.append(rec)
        self._by_sha[sha] = rec
        self.save()
        return rec

    def add_local(self, path: Path, *, kind: str = "local", record_meta: dict | None = None) -> dict:
        """تسجيل أصل محلي موجود (مكتبة الأيقونات أو أصل مصنوع)."""
        p = Path(path)
        sha = sha256_file(p)
        if sha in self._by_sha:
            return self._by_sha[sha]
        rec = {
            "sha256": sha,
            "path": str(p).replace("\\", "/"),
            "local": True,
            "bytes": p.stat().st_size,
            "kind": kind,
            "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        rec.update(record_meta or {})
        self.registry.append(rec)
        self._by_sha[sha] = rec
        self.save()
        return rec

    def save(self):
        write_json(self.registry_path, self.registry)

    # ---------- اعتمادات ----------
    def _approval_states(self) -> dict[str, str]:
        """The human decision per asset (from the project manifest), if any."""
        manifest = self.root / "project.json"
        if not manifest.exists():
            return {}
        try:
            data = read_json(manifest) or {}
        except Exception:
            return {}
        states: dict[str, str] = {}
        for asset in data.get("assets") or []:
            if not isinstance(asset, dict):
                continue
            path = str(asset.get("path") or "").replace("\\", "/")
            if not path:
                continue
            state = str((asset.get("approval") or {}).get("decision") or "pending")
            states[path] = state
        return states

    def credits_markdown(self) -> str:
        """The credits that must travel with the published video.

        Only the assets a human **approved** are credited: crediting a rejected
        asset would claim a licence relationship that does not exist, and
        crediting a deferred one would ship an asset that is not allowed yet.
        Deferred assets are listed separately so nothing disappears silently.
        """
        states = self._approval_states()
        lines = ["# اعتمادات الأصول (تُنشر مع الفيديو)", ""]
        attributions = [r for r in self.registry if r.get("license")]
        used: list[dict] = []
        pending: list[dict] = []
        for r in sorted(attributions, key=lambda x: (x.get("title") or "")):
            path = str(r.get("path") or "").replace("\\", "/")
            state = states.get(path)
            if state == "rejected":
                continue
            if state == "deferred":
                pending.append(r)
            else:
                used.append(r)
        for r in used:
            title = r.get("title") or r.get("path")
            author = r.get("author") or r.get("uploader") or ""
            lic = r.get("license") or ""
            src = r.get("page_url") or r.get("url") or r.get("source") or ""
            who = f" — {author}" if author else ""
            lines.append(f"- **{title}**{who} · {lic} · {src}")
        if len(lines) == 2:
            lines.append("(لا توجد أصول معتمدة تتطلب نسبًا)")
        if pending:
            lines += ["", "## أصول قيد الاعتماد (لم تُستخدم في هذا الفيديو)", ""]
            for r in pending:
                title = r.get("title") or r.get("path")
                lic = r.get("license") or ""
                lines.append(f"- {title} · {lic}")
        return "\n".join(lines)

    def write_credits(self) -> Path:
        p = self.root / "research" / "CREDITS.md"
        p.write_text(self.credits_markdown(), encoding="utf-8")
        return p
