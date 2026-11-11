from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
import shutil
from urllib.parse import urljoin, urlsplit
from uuid import uuid4

from bs4 import BeautifulSoup

from app.config import Settings
from app.fetcher import FetchError, PageFetcher
from app.outputs import OutputError, write_pdf
from app.parser import ArticleParser
from app.resources import ResourceDownloader
from app.storage import normalize_url, sanitize_filename
from app.topic_outputs import write_topic_epub, write_topic_html


class TopicFailure(RuntimeError):
    """A topic could not produce a usable output."""


@dataclass
class TopicArticle:
    position: int
    url: str
    title: str = ""
    body_html: str = ""
    work_assets: Path | None = None
    warnings: list[str] = field(default_factory=list)
    error: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "position": self.position,
            "url": self.url,
            "title": self.title,
            "status": "failed" if self.error else "success",
            "warnings": self.warnings,
            "error": self.error,
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


class TopicService:
    OUTPUT_FORMATS = {"html", "epub", "pdf"}

    def __init__(self, settings: Settings):
        self.settings = settings
        self.fetcher = PageFetcher(settings)
        self.parser = ArticleParser()
        self.resources = ResourceDownloader(settings)

    def download(self, topic_url: str, output_format: str = "html", concurrency: int = 1) -> TopicResult:
        selected_format = self.normalize_output_format(output_format)
        worker_count = self.normalize_concurrency(concurrency)
        snapshot = self.fetcher.fetch(topic_url)
        topic_title, article_urls = self.discover(snapshot.html, snapshot.final_url)
        if not article_urls:
            raise TopicFailure("专题中没有识别到可下载的 CSDN 文章")

        staging = self.settings.data_dir / ".staging" / f"topic-{uuid4().hex}"
        work_root = staging / "article-work"
        assets_root = staging / "assets"
        staging.mkdir(parents=True, exist_ok=True)
        articles: list[TopicArticle] = []
        try:
            with ThreadPoolExecutor(max_workers=worker_count) as executor:
                futures = [executor.submit(self._download_article, index, url, work_root) for index, url in enumerate(article_urls, 1)]
                for future in futures:
                    articles.append(future.result())
            articles.sort(key=lambda article: article.position)
            self._collect_assets(articles, assets_root)
            successful = [article for article in articles if not article.error]
            if not successful:
                reasons = "；".join(article.error or "未知错误" for article in articles)
                raise TopicFailure(f"专题没有生成任何可用文章：{reasons}")

            article_dicts = [self._article_output(article) for article in articles]
            output_path = staging / f"topic.{selected_format}"
            source_html = staging / "topic-source.html"
            if selected_format == "html":
                write_topic_html(output_path, topic_title, article_dicts)
            elif selected_format == "epub":
                write_topic_epub(output_path, topic_title, article_dicts, assets_root.glob("*"))
            else:
                write_topic_html(source_html, topic_title, article_dicts)
                write_pdf(source_html, output_path)
                source_html.unlink(missing_ok=True)

            warnings = [warning for article in articles for warning in article.warnings]
            failed = [article for article in articles if article.error]
            metadata = {
                "title": topic_title,
                "original_url": normalize_url(topic_url),
                "format": selected_format,
                "concurrency": worker_count,
                "articles": [article.as_dict() for article in articles],
                "warnings": warnings,
            }
            metadata_path = staging / "metadata.json"
            metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
            shutil.rmtree(work_root, ignore_errors=True)

            domain = (urlsplit(snapshot.final_url).hostname or "csdn.net").lower()
            topic_key = self._topic_key(topic_title, topic_url)
            target = self.settings.data_dir / domain / "topics" / topic_key
            self._commit(staging, target)
            return TopicResult(
                status="partial" if failed or warnings else "success",
                topic_title=topic_title,
                topic_url=topic_url,
                output_format=selected_format,
                output_path=target / f"topic.{selected_format}",
                metadata_path=target / "metadata.json",
                articles=articles,
                warnings=warnings,
            )
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
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
        title_node = soup.select_one("meta[property='og:title'], h1, title")
        title = (title_node.get("content") if title_node and title_node.name == "meta" else title_node.get_text(" ", strip=True) if title_node else "CSDN 专题") or "CSDN 专题"
        urls: list[str] = []
        seen: set[str] = set()
        for link in soup.select("a[href]"):
            absolute = normalize_url(urljoin(source_url, str(link.get("href"))))
            parsed = urlsplit(absolute)
            hostname = (parsed.hostname or "").lower()
            if hostname != "csdn.net" and not hostname.endswith(".csdn.net"):
                continue
            if "/article/details/" not in parsed.path or absolute in seen:
                continue
            seen.add(absolute)
            urls.append(absolute)
        return title.strip(), urls

    def _download_article(self, position: int, url: str, work_root: Path) -> TopicArticle:
        article = TopicArticle(position=position, url=url)
        try:
            snapshot = self.fetcher.fetch(url)
            parsed = self.parser.parse(snapshot.html, snapshot.final_url)
            article.title = parsed.metadata.title
            assets_dir = work_root / str(position) / "assets"
            resource_result = self.resources.download(parsed.body_html, snapshot.final_url, assets_dir)
            article.body_html = resource_result.body_html
            article.work_assets = assets_dir
            article.warnings.extend(resource_result.warnings)
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

    @staticmethod
    def _commit(staging: Path, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        backup = target.with_name(f".{target.name}.previous-{uuid4().hex}")
        if target.exists():
            target.replace(backup)
        try:
            staging.replace(target)
        except Exception:
            if backup.exists() and not target.exists():
                backup.replace(target)
            raise
        finally:
            if backup.exists():
                shutil.rmtree(backup, ignore_errors=True)
