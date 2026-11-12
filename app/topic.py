from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from dataclasses import dataclass, field
from itertools import batched
from pathlib import Path
import re
import shutil
from time import sleep
from typing import Literal
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from app.archive import ArchiveService
from app.outputs import write_pdf
from app.storage import ArchivePaths, normalize_url, sanitize_filename
from app.topic_outputs import write_topic_epub, write_topic_html


class TopicFailure(RuntimeError):
    """A topic could not produce a usable output."""

    def __init__(self, message: str, articles: list[TopicArticle] | None = None):
        super().__init__(message)
        self.articles = articles or []


@dataclass
class TopicArticle:
    position: int
    url: str
    title: str = ""
    body_html: str = ""
    work_assets: Path | None = None
    warnings: list[str] = field(default_factory=list)
    error: str | None = None
    source: Literal["web", "saved_html"] = "web"

    def as_dict(self) -> dict[str, object]:
        return {
            "position": self.position,
            "url": self.url,
            "title": self.title,
            "status": "failed" if self.error else "success",
            "warnings": self.warnings,
            "error": self.error,
            "source": self.source,
        }


@dataclass
class TopicResult:
    status: str
    topic_title: str
    topic_url: str
    output_format: str
    output_path: Path
    metadata_path: Path
    articles: list[TopicArticle]
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class TopicProgress:
    stage: Literal["discovering", "downloading", "exporting"] = "discovering"
    total: int = 0
    processed: int = 0
    failed: int = 0
    discovered_total: int = 0


class TopicService:
    OUTPUT_FORMATS = {"html", "epub", "pdf"}

    def __init__(self, archive_service: ArchiveService):
        self.archive_service = archive_service

    def download(
        self,
        topic_url: str,
        output_format: str = "html",
        concurrency: int = 1,
        *,
        on_progress: Callable[[TopicProgress], None] | None = None,
        saved_articles: dict[str, str] | None = None,
    ) -> TopicResult:
        selected_format = self.normalize_output_format(output_format)
        worker_count = self.normalize_concurrency(concurrency)
        snapshot = self.archive_service.fetcher.fetch(topic_url)
        topic_title, article_urls = self.discover(snapshot.html, snapshot.final_url)
        if not article_urls:
            raise TopicFailure("专题中没有识别到可下载的 CSDN 文章")

        store = self.archive_service.store
        article_limit = store.settings.topic_article_limit
        discovered_total = len(article_urls)
        if article_limit:
            article_urls = article_urls[:article_limit]
        local_articles = saved_articles or {}
        article_ids = {self._article_id(url) for url in article_urls}
        unmatched = local_articles.keys() - article_ids
        if unmatched:
            raise TopicFailure(f"这些 HTML 的文章 ID 不在本次下载范围内：{', '.join(sorted(unmatched))}")
        total = len(article_urls)
        if on_progress:
            on_progress(TopicProgress("downloading", total, discovered_total=discovered_total))
        staging = store.create_staging()
        work_root = staging.archive_dir / "article-work"
        assets_root = staging.assets
        articles: list[TopicArticle] = []
        failed_count = 0
        try:
            with ThreadPoolExecutor(max_workers=worker_count) as executor:
                for batch_number, batch in enumerate(batched(enumerate(article_urls, 1), worker_count)):
                    if batch_number:
                        sleep(1)
                    futures = [
                        executor.submit(
                            self._download_article,
                            index,
                            url,
                            work_root,
                            local_articles.get(self._article_id(url)),
                            referer=snapshot.final_url,
                        )
                        for index, url in batch
                    ]
                    for future in as_completed(futures):
                        article = future.result()
                        articles.append(article)
                        failed_count += int(bool(article.error))
                        if on_progress:
                            on_progress(
                                TopicProgress("downloading", total, len(articles), failed_count, discovered_total)
                            )
            articles.sort(key=lambda article: article.position)
            if failed_count == total:
                reasons = "；".join(dict.fromkeys(article.error or "未知错误" for article in articles))
                raise TopicFailure(f"专题没有生成任何可用文章：{reasons}", articles)

            if on_progress:
                on_progress(TopicProgress("exporting", total, len(articles), failed_count, discovered_total))
            self._collect_assets(articles, assets_root)
            article_dicts = [self._article_output(article) for article in articles]
            output_path = staging.archive_dir / f"topic.{selected_format}"
            source_html = staging.archive_dir / "topic-source.html"
            if selected_format == "html":
                write_topic_html(output_path, topic_title, article_dicts)
            elif selected_format == "epub":
                write_topic_epub(output_path, topic_title, article_dicts, assets_root.glob("*"))
            else:
                write_topic_html(source_html, topic_title, article_dicts)
                write_pdf(source_html, output_path)
                source_html.unlink(missing_ok=True)

            warnings = [warning for article in articles for warning in article.warnings]
            metadata = {
                "title": topic_title,
                "original_url": normalize_url(topic_url),
                "format": selected_format,
                "concurrency": worker_count,
                "discovered_article_count": discovered_total,
                "article_limit": article_limit,
                "articles": [article.as_dict() for article in articles],
                "warnings": warnings,
            }
            staging.metadata.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
            shutil.rmtree(work_root, ignore_errors=True)

            domain = (urlsplit(snapshot.final_url).hostname or "csdn.net").lower()
            topic_key = self._topic_key(topic_title, topic_url)
            if article_limit:
                topic_key = sanitize_filename(f"preview-{article_limit}-{topic_key}", max_length=150)
            target = ArchivePaths(store.settings.data_dir / domain / "topics" / topic_key)
            store.commit(staging, target)
            return TopicResult(
                status="partial" if failed_count or warnings else "success",
                topic_title=topic_title,
                topic_url=topic_url,
                output_format=selected_format,
                output_path=target.archive_dir / output_path.name,
                metadata_path=target.metadata,
                articles=articles,
                warnings=warnings,
            )
        except Exception:
            store.cleanup_staging(staging)
            raise

    @classmethod
    def normalize_output_format(cls, value: str) -> str:
        selected = str(value or "").strip().lower()
        if selected not in cls.OUTPUT_FORMATS:
            raise ValueError("专题输出格式只能选择 HTML、EPUB 或 PDF 其中一种")
        return selected

    @staticmethod
    def normalize_concurrency(value: int | str) -> int:
        try:
            selected = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("专题并行数量必须是正整数") from exc
        if selected < 1:
            raise ValueError("专题并行数量必须是正整数")
        return selected

    @staticmethod
    def discover(html: str, source_url: str) -> tuple[str, list[str]]:
        soup = BeautifulSoup(html, "lxml")
        column_list = soup.select_one("#column .column_article_list")
        is_column = column_list is not None or re.search(r"/category_\d+(?:_\d+)?\.html$", urlsplit(source_url).path)
        if is_column:
            title_node = soup.select_one("#column .column_title")
            title = title_node.get_text(" ", strip=True) if title_node else ""
            links = column_list.select(":scope > li > a[href]") if column_list is not None else []
        else:
            title_node = soup.select_one("meta[property='og:title'], h1, title")
            title = ""
            if title_node is not None:
                title = title_node.get("content", "") if title_node.name == "meta" else title_node.get_text(" ", strip=True)
            links = soup.select("a[href]")
        urls: list[str] = []
        seen: set[str] = set()
        for link in links:
            absolute = normalize_url(urljoin(source_url, str(link.get("href"))))
            parsed = urlsplit(absolute)
            hostname = (parsed.hostname or "").lower()
            if parsed.scheme not in {"http", "https"} or (hostname != "csdn.net" and not hostname.endswith(".csdn.net")):
                continue
            if "/article/details/" not in parsed.path or absolute in seen:
                continue
            seen.add(absolute)
            urls.append(absolute)
        return title.strip() or "CSDN 专题", urls

    @staticmethod
    def _article_id(url: str) -> str:
        return urlsplit(url).path.rstrip("/").rsplit("/", 1)[-1]

    def _download_article(
        self,
        position: int,
        url: str,
        work_root: Path,
        saved_html: str | None = None,
        *,
        referer: str | None = None,
    ) -> TopicArticle:
        article = TopicArticle(position=position, url=url)
        try:
            assets_dir = work_root / str(position) / "assets"
            if saved_html is None:
                prepared = self.archive_service.prepare_article(url, assets_dir, referer=referer)
            else:
                article.source = "saved_html"
                prepared = self.archive_service.prepare_saved_article(url, saved_html, assets_dir)
            article.title = prepared.metadata.title
            article.body_html = prepared.body_html
            article.work_assets = assets_dir
            article.warnings.extend(prepared.warnings)
        except Exception as exc:
            article.error = str(exc)
        return article

    @staticmethod
    def _collect_assets(articles: list[TopicArticle], assets_root: Path) -> None:
        assets_root.mkdir(parents=True, exist_ok=True)
        for article in articles:
            if article.error or not article.work_assets or not article.work_assets.exists():
                continue
            for source in article.work_assets.iterdir():
                if not source.is_file():
                    continue
                target_name = f"article-{article.position}-{sanitize_filename(source.name, max_length=80, fallback='asset')}"
                target = assets_root / target_name
                shutil.copy2(source, target)
                article.body_html = article.body_html.replace(f"assets/{source.name}", f"assets/{target_name}")

    @staticmethod
    def _article_output(article: TopicArticle) -> dict[str, object]:
        return {
            "position": article.position,
            "title": article.title or f"文章 {article.position}",
            "body_html": article.body_html,
            "error": article.error,
        }

    @staticmethod
    def _topic_key(title: str, url: str) -> str:
        digest = hashlib.sha256(normalize_url(url).encode("utf-8")).hexdigest()[:12]
        return sanitize_filename(f"topic-{digest}_{title}", max_length=150, fallback=f"topic-{digest}")
