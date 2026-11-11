from __future__ import annotations

import hashlib
import json
import re
import shutil
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from app.config import Settings
from app.models import ArticleMetadata


INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
WHITESPACE = re.compile(r"\s+")
WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, parts.query, ""))


def sanitize_filename(value: str, max_length: int = 96, fallback: str = "article") -> str:
    normalized = unicodedata.normalize("NFKC", value or "")
    normalized = INVALID_FILENAME_CHARS.sub("_", normalized)
    normalized = WHITESPACE.sub(" ", normalized).strip(" .")
    normalized = normalized[:max_length].rstrip(" .")
    if not normalized:
        normalized = fallback
    if normalized.upper() in WINDOWS_RESERVED_NAMES:
        normalized = f"_{normalized}"
    return normalized


def article_key(article_id: str | None, title: str, original_url: str) -> str:
    clean_title = sanitize_filename(title, fallback="article")
    if article_id and sanitize_filename(article_id, fallback=""):
        clean_id = sanitize_filename(article_id, max_length=48, fallback="article")
    else:
        digest = hashlib.sha256(normalize_url(original_url).encode("utf-8")).hexdigest()[:12]
        clean_id = f"url-{digest}"
    return sanitize_filename(f"{clean_id}_{clean_title}", max_length=150)


@dataclass(frozen=True)
class ArchivePaths:
    archive_dir: Path

    @property
    def html(self) -> Path:
        return self.archive_dir / "article.html"

    @property
    def pdf(self) -> Path:
        return self.archive_dir / "article.pdf"

    @property
    def metadata(self) -> Path:
        return self.archive_dir / "metadata.json"

    @property
    def assets(self) -> Path:
        return self.archive_dir / "assets"


class ArchiveStore:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.settings.ensure_directories()
        self.staging_root = self.settings.data_dir / ".staging"
        self.staging_root.mkdir(parents=True, exist_ok=True)

    def paths_for(self, metadata: ArticleMetadata) -> ArchivePaths:
        return ArchivePaths(self.settings.data_dir / metadata.domain / article_key(metadata.article_id, metadata.title, metadata.original_url))

    def create_staging(self) -> ArchivePaths:
        return ArchivePaths(self.staging_root / uuid4().hex)

    def write_metadata(self, paths: ArchivePaths, metadata: ArticleMetadata) -> None:
        paths.archive_dir.mkdir(parents=True, exist_ok=True)
        paths.metadata.write_text(json.dumps(metadata.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    def commit(self, staging: ArchivePaths, target: ArchivePaths) -> None:
        if not staging.archive_dir.exists():
            raise FileNotFoundError(f"staging archive does not exist: {staging.archive_dir}")
        target.archive_dir.parent.mkdir(parents=True, exist_ok=True)
        backup = target.archive_dir.with_name(f".{target.archive_dir.name}.previous-{uuid4().hex}")
        if target.archive_dir.exists():
            target.archive_dir.replace(backup)
        try:
            staging.archive_dir.replace(target.archive_dir)
        except Exception:
            if backup.exists() and not target.archive_dir.exists():
                backup.replace(target.archive_dir)
            raise
        finally:
            if backup.exists():
                shutil.rmtree(backup, ignore_errors=True)

    def cleanup_staging(self, staging: ArchivePaths) -> None:
        if staging.archive_dir.exists():
            shutil.rmtree(staging.archive_dir, ignore_errors=True)
