from __future__ import annotations

import hashlib
import json
import re
import shutil
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from time import sleep
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

_WINDOWS_MOVE_RETRY_DELAYS = (0.05, 0.15, 0.35)
_WINDOWS_MOVE_ERRORS = {5, 32, 33}


def _windows_move_denied(error: OSError) -> bool:
    return getattr(error, "winerror", None) in _WINDOWS_MOVE_ERRORS


def _replace_archive_directory(source: Path, target: Path) -> None:
    for delay in _WINDOWS_MOVE_RETRY_DELAYS:
        try:
            source.replace(target)
            return
        except OSError as exc:
            if not _windows_move_denied(exc):
                raise
            sleep(delay)
    source.replace(target)


def _publish_archive_directory(source: Path, target: Path) -> None:
    try:
        _replace_archive_directory(source, target)
        return
    except OSError as exc:
        if not _windows_move_denied(exc):
            raise

    incoming = target.with_name(f".incoming-{uuid4().hex}")
    try:
        shutil.copytree(source, incoming, symlinks=True)
        _replace_archive_directory(incoming, target)
    finally:
        shutil.rmtree(incoming, ignore_errors=True)


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
    clean_title = sanitize_filename(title, max_length=52, fallback="article")
    if article_id and sanitize_filename(article_id, fallback=""):
        clean_id = sanitize_filename(article_id, max_length=48, fallback="article")
    else:
        digest = hashlib.sha256(normalize_url(original_url).encode("utf-8")).hexdigest()[:12]
        clean_id = f"url-{digest}"
    return sanitize_filename(f"{clean_id}_{clean_title}", max_length=150)


def topic_identifier(url: str) -> str:
    parsed = urlsplit(url)
    category = re.search(r"/category_([0-9]{1,24})(?:_[0-9]+)?\.html$", parsed.path)
    if category and parsed.hostname == "blog.csdn.net":
        return category[1]
    return "url-" + hashlib.sha256(normalize_url(url).encode("utf-8")).hexdigest()[:12]


def topic_directory(data_dir: Path, title: str, url: str) -> Path:
    root = data_dir / "topics"
    identifier = topic_identifier(url)
    for candidate in sorted(root.glob(f"{identifier}_*")):
        if candidate.is_dir() and candidate.resolve() == candidate:
            return candidate
    return root / f"{identifier}_{sanitize_filename(title, max_length=52, fallback='专题')}"


def topic_scope(article_limit: int) -> str:
    return f"前{article_limit}篇" if article_limit else "全部"


def read_archive_aliases(data_dir: Path) -> dict[str, str]:
    try:
        values = json.loads((data_dir / ".internal" / "archive-aliases.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    if not isinstance(values, dict) or any(not isinstance(target, str) for target in values.values()):
        raise ValueError("归档链接映射格式无效。")
    return values


def alias_target(data_dir: Path, legacy: Path) -> Path | None:
    try:
        target = read_archive_aliases(data_dir).get(legacy.as_posix())
        if target is None:
            return None
        path = (data_dir / target).resolve()
    except (OSError, ValueError, RuntimeError):
        return None
    if not any(root in path.parents for root in (data_dir / "articles", data_dir / "topics")):
        return None
    return path


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
    def md(self) -> Path:
        return self.archive_dir / "article.md"

    @property
    def metadata(self) -> Path:
        return self.archive_dir / "metadata.json"

    @property
    def assets(self) -> Path:
        return self.archive_dir / "assets"

    def article_outputs(self) -> dict[str, Path]:
        return {
            name: path for name, path in (("html", self.html), ("pdf", self.pdf), ("md", self.md))
            if path.is_file() and not path.is_symlink()
        }


class ArchiveStore:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.settings.ensure_directories()
        self.staging_root = self.settings.data_dir / ".internal" / "staging"
        self.staging_root.mkdir(parents=True, exist_ok=True)

    def paths_for(self, metadata: ArticleMetadata) -> ArchivePaths:
        return ArchivePaths(self.settings.data_dir / "articles" / article_key(
            metadata.article_id, metadata.title, metadata.original_url
        ))

    def create_staging(self) -> ArchivePaths:
        return ArchivePaths(self.staging_root / uuid4().hex)

    def write_metadata(self, paths: ArchivePaths, metadata: ArticleMetadata) -> None:
        paths.archive_dir.mkdir(parents=True, exist_ok=True)
        paths.metadata.write_text(json.dumps(metadata.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    def retain_article_outputs(self, staging: ArchivePaths, previous: ArchivePaths) -> None:
        retained = previous.article_outputs().keys() - staging.article_outputs().keys()
        for name in retained:
            shutil.copy2(getattr(previous, name), getattr(staging, name))
        if retained & {"html", "md"} and not previous.assets.is_symlink() and previous.assets.is_dir():
            shutil.copytree(previous.assets, staging.assets, dirs_exist_ok=True, symlinks=True)

    def commit(self, staging: ArchivePaths, target: ArchivePaths) -> None:
        if not staging.archive_dir.exists():
            raise FileNotFoundError(f"staging archive does not exist: {staging.archive_dir}")
        target.archive_dir.parent.mkdir(parents=True, exist_ok=True)
        backup = target.archive_dir.with_name(f".{target.archive_dir.name}.previous-{uuid4().hex}")
        if target.archive_dir.exists():
            _replace_archive_directory(target.archive_dir, backup)
        try:
            _publish_archive_directory(staging.archive_dir, target.archive_dir)
        except Exception:
            if backup.exists() and not target.archive_dir.exists():
                try:
                    _replace_archive_directory(backup, target.archive_dir)
                except OSError as exc:
                    raise OSError(f"无法恢复归档目录，原文件保留在 {backup}") from exc
            raise
        else:
            if backup.exists():
                shutil.rmtree(backup, ignore_errors=True)
            self.cleanup_staging(staging)

    def cleanup_staging(self, staging: ArchivePaths) -> None:
        if staging.archive_dir.exists():
            shutil.rmtree(staging.archive_dir, ignore_errors=True)
