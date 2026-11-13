from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from dataclasses import dataclass, field, replace
from itertools import batched
from pathlib import Path
import re
import shutil
from time import sleep
from typing import Literal
from urllib.parse import urljoin, urlsplit
from uuid import uuid4
from zipfile import BadZipFile, ZipFile

from bs4 import BeautifulSoup

from app.archive import ArchiveService
from app.markdown import write_topic_markdown
from app.outputs import OutputError, write_pdf
from app.storage import ArchivePaths, normalize_url, sanitize_filename, topic_directory, topic_scope
from app.topic_outputs import write_topic_epub, write_topic_html


class TopicFailure(RuntimeError):
    """A topic could not produce a usable output."""

    def __init__(
        self, message: str, articles: list[TopicArticle] | None = None, *, attempt: TopicAttempt | None = None
    ):
        super().__init__(message)
        self.articles = articles or []
        self.attempt = attempt


def _article_id(url: str) -> str:
    return urlsplit(url).path.rstrip("/").rsplit("/", 1)[-1]


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

    @property
    def article_id(self) -> str:
        return _article_id(self.url)

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
class TopicAttempt:
    topic_title: str
    topic_url: str
    output_format: str
    concurrency: int
    article_limit: int
    discovered_total: int
    target: ArchivePaths
    articles: list[TopicArticle]

    @property
    def output_path(self) -> Path:
        return self.target.archive_dir / f"topic.{self.output_format}"

    def as_result(self) -> TopicResult:
        warnings = [warning for article in self.articles for warning in article.warnings]
        return TopicResult(
            status="partial" if warnings or any(article.error for article in self.articles) else "success",
            topic_title=self.topic_title,
            topic_url=self.topic_url,
            output_format=self.output_format,
            output_path=self.output_path,
            metadata_path=self.target.metadata,
            articles=self.articles,
            warnings=warnings,
        )


@dataclass(frozen=True)
class TopicProgress:
    stage: Literal["discovering", "downloading", "exporting"] = "discovering"
    total: int = 0
    processed: int = 0
    failed: int = 0
    discovered_total: int = 0


class TopicService:
    OUTPUT_FORMATS = ("html", "epub", "pdf", "md")
    BODY_CACHE = ".article-bodies.json"

    def __init__(self, archive_service: ArchiveService):
        self.archive_service = archive_service

    def download(
        self,
        topic_url: str,
        output_format: str = "html",
        concurrency: int = 1,
        *,
        article_limit: int | None = None,
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
        article_limit = self.normalize_article_limit(
            store.settings.topic_article_limit if article_limit is None else article_limit
        )
        discovered_total = len(article_urls)
        if article_limit:
            article_urls = article_urls[:article_limit]
        local_articles = saved_articles or {}
        article_ids = {_article_id(url) for url in article_urls}
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
                            local_articles.get(_article_id(url)),
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
            topic_dir = topic_directory(store.settings.data_dir, topic_title, topic_url)
            target = ArchivePaths(topic_dir / topic_scope(article_limit) / selected_format)
            attempt = TopicAttempt(
                topic_title, topic_url, selected_format, worker_count, article_limit, discovered_total, target, articles
            )
            if failed_count == total:
                reasons = "；".join(dict.fromkeys(article.error or "未知错误" for article in articles))
                raise TopicFailure(f"专题没有生成任何可用文章：{reasons}", articles, attempt=attempt)

            if on_progress:
                on_progress(TopicProgress("exporting", total, len(articles), failed_count, discovered_total))
            self._collect_assets(articles, assets_root)
            shutil.rmtree(work_root, ignore_errors=True)
            return self._export(attempt, staging)
        except Exception:
            store.cleanup_staging(staging)
            raise

    def retry_article(
        self, attempt: TopicAttempt, position: int, *, on_progress: Callable[[TopicProgress], None],
        saved_html: str | None = None,
    ) -> TopicResult:
        previous = next((article for article in attempt.articles if article.position == position and article.error), None)
        if previous is None:
            raise ValueError("这篇文章当前无需重试。")
        total = len(attempt.articles)
        failed = sum(bool(article.error) for article in attempt.articles)
        has_saved_articles = failed < total
        if has_saved_articles and not attempt.output_path.is_file():
            raise ValueError("原专题输出已不存在，请重新下载专题。")
        if not has_saved_articles and attempt.target.archive_dir.exists():
            target = attempt.target.archive_dir
            retry_key = sanitize_filename(f"{target.name}-重试-{uuid4().hex[:8]}", max_length=150)
            attempt = replace(attempt, target=ArchivePaths(target.with_name(retry_key)))
        on_progress(TopicProgress("downloading", total, total - 1, failed - 1, attempt.discovered_total))
        store = self.archive_service.store
        staging = store.create_staging()
        work_root = staging.archive_dir / "article-work"
        try:
            retried = self._download_article(position, previous.url, work_root, saved_html, referer=attempt.topic_url)
            articles = [retried if article is previous else replace(article) for article in attempt.articles]
            updated = replace(attempt, articles=articles)
            if retried.error:
                on_progress(TopicProgress("downloading", total, total, failed, attempt.discovered_total))
                if has_saved_articles:
                    return updated.as_result()
                raise TopicFailure(retried.error, articles, attempt=updated)
            on_progress(TopicProgress("exporting", total, total, failed - 1, attempt.discovered_total))
            if has_saved_articles:
                bodies = self.archived_bodies(attempt)
                for article in articles:
                    if article is not retried and not article.error:
                        if str(article.position) not in bodies:
                            raise ValueError("已有归档缺少正文，无法合并。请重新下载专题。")
                        article.body_html = bodies[str(article.position)]
                staging.assets.mkdir(parents=True, exist_ok=True)
                for asset in attempt.target.assets.glob("*"):
                    if asset.resolve() == asset and asset.is_file():
                        shutil.copy2(asset, staging.assets / asset.name)
            self._collect_assets([retried], staging.assets)
            shutil.rmtree(work_root, ignore_errors=True)
            return self._export(updated, staging)
        except (OSError, ValueError, OutputError) as exc:
            raise TopicFailure(f"重试后无法更新专题：{exc}", attempt.articles, attempt=attempt) from exc
        finally:
            store.cleanup_staging(staging)

    def _export(self, attempt: TopicAttempt, staging: ArchivePaths) -> TopicResult:
        article_dicts = [self._article_output(article) for article in attempt.articles]
        output_path = staging.archive_dir / attempt.output_path.name
        source_url = normalize_url(attempt.topic_url)
        if attempt.output_format == "html":
            write_topic_html(output_path, attempt.topic_title, article_dicts, source_url=source_url)
        elif attempt.output_format == "epub":
            write_topic_epub(output_path, attempt.topic_title, article_dicts, staging.assets.glob("*"), source_url=source_url)
        elif attempt.output_format == "md":
            write_topic_markdown(output_path, attempt.topic_title, article_dicts, source_url=source_url)
        else:
            source_html = staging.archive_dir / "topic-source.html"
            write_topic_html(source_html, attempt.topic_title, article_dicts, source_url=source_url)
            write_pdf(source_html, output_path)
            source_html.unlink()
        result = attempt.as_result()
        metadata = {
            "title": attempt.topic_title,
            "original_url": source_url,
            "format": attempt.output_format,
            "concurrency": attempt.concurrency,
            "discovered_article_count": attempt.discovered_total,
            "article_limit": attempt.article_limit,
            "articles": [article.as_dict() for article in attempt.articles],
            "warnings": result.warnings,
        }
        staging.metadata.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        bodies = {str(article.position): article.body_html for article in attempt.articles if not article.error}
        (staging.archive_dir / self.BODY_CACHE).write_text(json.dumps(bodies, ensure_ascii=False), encoding="utf-8")
        self.archive_service.store.commit(staging, attempt.target)
        return result

    @classmethod
    def archived_bodies(cls, attempt: TopicAttempt) -> dict[str, str]:
        cache = attempt.target.archive_dir / cls.BODY_CACHE
        if cache.resolve() == cache and cache.is_file():
            bodies = json.loads(cache.read_text(encoding="utf-8"))
            if isinstance(bodies, dict) and all(isinstance(body, str) for body in bodies.values()):
                return bodies
            raise ValueError("归档正文记录已损坏，请重新下载专题。")
        if attempt.output_format == "html":
            html = attempt.output_path.read_text(encoding="utf-8")
        elif attempt.output_format == "epub":
            try:
                with ZipFile(attempt.output_path) as book:
                    html = book.read("OEBPS/content.xhtml").decode("utf-8")
            except (BadZipFile, KeyError, UnicodeError) as exc:
                raise ValueError("无法读取旧 EPUB 的正文。请重新下载专题。") from exc
        else:
            raise ValueError("归档缺少可合并的正文。请重新下载专题。")
        soup = BeautifulSoup(html, "lxml")
        bodies = {}
        for section in soup.select("main > section.topic-article[id]"):
            source_note = section.select_one(":scope > h2 + p.archive-source")
            if source_note is not None:
                source_note.decompose()
            heading = section.find("h2", recursive=False)
            if heading is not None:
                heading.decompose()
            for block in section.select("details.code-block"):
                summary = block.find("summary", recursive=False)
                if summary is not None:
                    summary.decompose()
                block.unwrap()
            bodies[section["id"].removeprefix("article-")] = section.decode_contents()
        return bodies

    @classmethod
    def normalize_output_format(cls, value: str) -> str:
        selected = str(value or "").strip().lower()
        if selected not in cls.OUTPUT_FORMATS:
            raise ValueError("专题输出格式只能选择 HTML、EPUB、PDF 或 Markdown 其中一种")
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
    def normalize_article_limit(value: int | str) -> int:
        try:
            selected = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("下载篇数必须是非负整数，填 0 下载全部。") from exc
        if selected < 0:
            raise ValueError("下载篇数必须是非负整数，填 0 下载全部。")
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
            "url": article.url,
            "title": article.title or f"文章 {article.position}",
            "body_html": article.body_html,
            "error": article.error,
        }
