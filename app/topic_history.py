from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re

from app.fetcher import FetchError, PageFetcher
from app.storage import ArchivePaths, normalize_url, topic_identifier
from app.topic import TopicArticle, TopicAttempt, TopicService


@dataclass(frozen=True)
class TopicArchive:
    attempt: TopicAttempt
    saved_at: datetime

    @property
    def identity(self) -> str:
        url = self.attempt.topic_url
        return topic_identifier(url) if url else str(self.attempt.target.archive_dir)

    @property
    def can_retry(self) -> bool:
        cache = self.attempt.target.archive_dir / TopicService.BODY_CACHE
        return bool(self.attempt.topic_url) and (
            self.attempt.output_format in {"html", "epub"}
            or (not cache.is_symlink() and cache.is_file())
        )


def _saved_articles(entries: object) -> list[TopicArticle]:
    articles: dict[int, TopicArticle] = {}
    if not isinstance(entries, list):
        return []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        position, url = entry.get("position"), entry.get("url")
        if type(position) is not int or position < 1 or not isinstance(url, str):
            continue
        try:
            PageFetcher.validate_url(url)
        except (FetchError, ValueError):
            continue
        error = entry.get("error")
        if not error and entry.get("status") == "failed":
            error = "下载失败"
        warnings = entry.get("warnings")
        articles[position] = TopicArticle(
            position=position,
            url=url,
            title=str(entry.get("title") or ""),
            error=str(error) if error else None,
            warnings=[str(warning) for warning in warnings] if isinstance(warnings, list) else [],
            source="saved_html" if entry.get("source") == "saved_html" else "web",
        )
    return sorted(articles.values(), key=lambda article: article.position)


def read_topic_archive(archive_dir: Path) -> TopicArchive | None:
    target = ArchivePaths(archive_dir)
    try:
        metadata_path = target.metadata
        if metadata_path.resolve() != metadata_path or not metadata_path.is_file():
            return None
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if not isinstance(metadata, dict):
            return None
        title = metadata.get("title")
        if not isinstance(title, str) or not title.strip():
            return None
        output_format = TopicService.normalize_output_format(metadata.get("format"))
        output = archive_dir / f"topic.{output_format}"
        if output.resolve() != output or not output.is_file():
            return None
        saved_at = datetime.fromtimestamp(output.stat().st_mtime).astimezone()
        articles = _saved_articles(metadata.get("articles"))
        preview = re.match(r"(?:retry-[0-9a-f]+-)?preview-([0-9]+)-", archive_dir.name)
        limit = metadata.get("article_limit", preview[1] if preview else 0)
        url = metadata.get("original_url") or ""
        if url:
            url = normalize_url(PageFetcher.validate_url(str(url)))
        attempt = TopicAttempt(
            title.strip(), url, output_format,
            TopicService.normalize_concurrency(metadata.get("concurrency", 1)),
            TopicService.normalize_article_limit(limit),
            max(len(articles), int(metadata.get("discovered_article_count", 0))),
            target, articles,
        )
    except (OSError, RuntimeError, ValueError, TypeError, OverflowError):
        return None
    return TopicArchive(attempt, saved_at)


def list_topic_archives(data_dir: Path) -> list[TopicArchive]:
    records = []
    root = data_dir.resolve()
    for pattern in ("[!.]*/topics/[!.]*/metadata.json", "topics/[!.]*/[!.]*/[!.]*/metadata.json"):
        for path in root.glob(pattern):
            if record := read_topic_archive(path.parent):
                records.append(record)
    return sorted(records, key=lambda record: (record.saved_at, record.attempt.output_path), reverse=True)


def group_topic_archives(data_dir: Path, *, output_format: str = "") -> list[list[TopicArchive]]:
    groups: dict[str, list[TopicArchive]] = {}
    for record in list_topic_archives(data_dir):
        if not output_format or record.attempt.output_format == output_format:
            groups.setdefault(record.identity, []).append(record)
    return list(groups.values())
