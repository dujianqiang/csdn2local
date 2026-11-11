from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile

import pytest

import app.topic as topic_module
from app.config import Settings
from app.fetcher import FetchError, PageSnapshot
from app.parser import ParsedArticle
from app.models import ArticleMetadata
from app.resources import ResourceDownloadResult
from app.topic import TopicService


TOPIC_URL = "https://blog.csdn.net/demo/topic"
ARTICLE_ONE = "https://blog.csdn.net/demo/article/details/1"
ARTICLE_TWO = "https://blog.csdn.net/demo/article/details/2"


class FakeFetcher:
    def __init__(self, failed: str | None = None):
        self.failed = failed

    def fetch(self, url: str) -> PageSnapshot:
        if url == TOPIC_URL:
            html = f"<html><head><title>测试专题</title></head><body><a href='{ARTICLE_ONE}'>一</a><a href='{ARTICLE_TWO}'>二</a><a href='{ARTICLE_ONE}'>重复</a></body></html>"
            return PageSnapshot(url, url, html)
        if url == self.failed:
            raise FetchError("文章访问失败")
        return PageSnapshot(url, url, "<html><article>正文</article></html>")


class FakeParser:
    def parse(self, html: str, source_url: str) -> ParsedArticle:
        number = source_url.rsplit("/", 1)[-1]
        metadata = ArticleMetadata(
            title=f"文章 {number}",
            original_url=source_url,
            domain="blog.csdn.net",
            article_id=number,
        )
        return ParsedArticle(metadata, f"<p>正文 {number}</p>", [])


class FakeResources:
    def download(self, body_html: str, source_url: str, assets_dir: Path) -> ResourceDownloadResult:
        assets_dir.mkdir(parents=True, exist_ok=True)
        return ResourceDownloadResult(body_html, [])


def make_service(tmp_path: Path, failed: str | None = None) -> TopicService:
    service = TopicService(Settings.from_project_root(tmp_path))
    service.fetcher = FakeFetcher(failed)
    service.parser = FakeParser()
    service.resources = FakeResources()
    return service


def test_discover_topic_links_preserves_order_and_deduplicates() -> None:
    title, urls = TopicService.discover(
        f"<html><head><meta property='og:title' content='专题标题'></head><body><a href='{ARTICLE_TWO}'>2</a><a href='{ARTICLE_ONE}'>1</a><a href='{ARTICLE_TWO}'>重复</a><a href='https://example.com/article/details/3'>外部</a></body></html>",
        TOPIC_URL,
    )

    assert title == "专题标题"
    assert urls == [ARTICLE_TWO, ARTICLE_ONE]


def test_topic_download_preserves_order_and_selected_epub(tmp_path: Path) -> None:
    service = make_service(tmp_path)

    result = service.download(TOPIC_URL, "epub", 2)

    assert result.status == "success"
    assert result.output_format == "epub"
    assert result.output_path.exists()
    assert [article.title for article in result.articles] == ["文章 1", "文章 2"]
    with ZipFile(result.output_path) as book:
        assert book.read("mimetype") == b"application/epub+zip"
        navigation = book.read("OEBPS/nav.xhtml").decode("utf-8")
        assert navigation.index("文章 1") < navigation.index("文章 2")
        assert "nav" in book.read("OEBPS/package.opf").decode("utf-8")


def test_topic_download_continues_after_article_failure(tmp_path: Path) -> None:
    service = make_service(tmp_path, ARTICLE_TWO)

    result = service.download(TOPIC_URL, "html", 1)

    assert result.status == "partial"
    assert result.output_path.exists()
    assert result.articles[0].error is None
    assert "文章访问失败" in (result.articles[1].error or "")
    html = result.output_path.read_text(encoding="utf-8")
    assert html.index("文章 1") < html.index("文章 2")
    assert "下载失败" in html


def test_topic_download_generates_selected_pdf(monkeypatch, tmp_path: Path) -> None:
    service = make_service(tmp_path)

    def fake_write_pdf(html_path: Path, pdf_path: Path) -> None:
        assert html_path.exists()
        pdf_path.write_bytes(b"%PDF-topic")

    monkeypatch.setattr(topic_module, "write_pdf", fake_write_pdf)
    result = service.download(TOPIC_URL, "pdf", 1)

    assert result.output_path.name == "topic.pdf"
    assert result.output_path.read_bytes().startswith(b"%PDF")


def test_topic_output_and_concurrency_validation() -> None:
    assert TopicService.normalize_output_format("EPUB") == "epub"
    assert TopicService.normalize_concurrency("1") == 1
    with pytest.raises(ValueError):
        TopicService.normalize_output_format("html,pdf")
    with pytest.raises(ValueError):
        TopicService.normalize_concurrency(0)
