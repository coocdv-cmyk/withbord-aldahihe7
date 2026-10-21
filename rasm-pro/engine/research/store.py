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
        """The latest human decision per project-relative asset path."""
        manifest = self.root / "project.json"
        path_to_id: dict[str, str] = {}
        states: dict[str, str] = {}
        if manifest.exists():
            try:
                data = read_json(manifest) or {}
            except Exception:
                data = {}
            for asset in data.get("assets") or []:
                if not isinstance(asset, dict):
                    continue
                path = str(asset.get("path") or "").replace("\\", "/")
                if not path:
                    continue
                asset_id = str(asset.get("asset_id") or "")
                if asset_id:
                    path_to_id[path] = asset_id
                states[path] = str(
                    (asset.get("approval") or {}).get("decision") or "pending"
                )
        # The append-only decision log is authoritative; the manifest is only
        # a projection and may lag behind the last human decision.
        try:
            from ..core.assets import decisions_by_asset

            decisions = decisions_by_asset(self.root)
        except Exception:
            decisions = {}
        for path, asset_id in path_to_id.items():
            records = decisions.get(asset_id) or []
            if records:
                states[path] = str(records[-1].get("decision") or "pending")
        return states

    def _relative_path(self, raw: str) -> str:
        path = str(raw or "").replace("\\", "/")
        if not path:
            return ""
        p = Path(path)
        if p.is_absolute():
            try:
                return p.resolve().relative_to(self.root.resolve()).as_posix()
            except ValueError:
                return path
        return path.lstrip("./")

    def credits_markdown(self, plan: dict | None = None) -> str:
        """Credits for **this video**: assets used by the plan *and* approved.

        A licence relationship only exists for assets that appear in the
        episode and were approved by a human.  Rejected assets are never
        credited; approved-but-unused assets are absent; deferred used assets
        are disclosed separately because they are not cleared for publication.
        """
        states = self._approval_states()
        used_paths: set[str] = set()
        if isinstance(plan, dict):
            try:
                from ..core.assets import plan_asset_refs

                manifest = None
                if (self.root / "project.json").exists():
                    try:
                        manifest = read_json(self.root / "project.json") or None
                    except Exception:
                        manifest = None
                used_paths = {
                    self._relative_path(ref.path)
                    for ref in plan_asset_refs(plan, self.root, manifest=manifest)
                    if ref.path
                }
            except Exception as exc:
                log.warning("تعذّر استخراج أصول الخطة للاعتمادات: %s", exc)

        by_path = {
            self._relative_path(str(r.get("path") or "")): r for r in self.registry
        }
        credited: list[dict] = []
        deferred: list[dict] = []
        not_approved: list[dict] = []
        unattributed: list[str] = []
        for path in sorted(used_paths):
            rec = by_path.get(path)
            if rec is None:
                unattributed.append(path)
                continue
            state = states.get(path, "pending")
            if state == "rejected":
                continue
            if state == "deferred":
                deferred.append(rec)
                continue
            if state != "approved":
                not_approved.append(rec)
                continue
            if not rec.get("license"):
                unattributed.append(path)
                continue
            credited.append(rec)

        lines = ["# اعتمادات الأصول (تُنشر مع الفيديو)", ""]
        for r in sorted(credited, key=lambda x: (x.get("title") or x.get("path") or "")):
            title = r.get("title") or r.get("path")
            author = r.get("author") or r.get("uploader") or ""
            lic = r.get("license") or ""
            src = r.get("page_url") or r.get("url") or r.get("source") or ""
            who = f" — {author}" if author else ""
            lines.append(f"- **{title}**{who} · {lic} · {src}")
        if not credited:
            lines.append("(لا توجد أصول معتمدة ومستخدمة تتطلب نسبًا)")

        def section(title: str, records: list[dict], extra: str = "") -> None:
            if not records:
                return
            lines.extend(["", f"## {title}", ""])
            if extra:
                lines.extend([extra, ""])
            for r in sorted(records, key=lambda x: (x.get("title") or x.get("path") or "")):
                title = r.get("title") or r.get("path")
                lic = r.get("license") or "بلا ترخيص"
                lines.append(f"- {title} · {lic}")

        section("أصول مستخدمة قيد الاعتماد", deferred, "لم تُعتمد بعد — لا تُنشر.")
        section("أصول مستخدمة بانتظار قرار", not_approved)
        if unattributed:
            lines.extend(["", "## أصول مستخدمة بلا تسجيل/ترخيص", ""])
            lines.extend(f"- {path}" for path in unattributed)
        return "\n".join(lines)

    def write_credits(self, plan: dict | None = None) -> Path:
        p = self.root / "research" / "CREDITS.md"
        p.write_text(self.credits_markdown(plan=plan), encoding="utf-8")
        return p
