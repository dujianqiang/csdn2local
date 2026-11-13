from __future__ import annotations

import json
import sys
from pathlib import Path
from threading import Event
from unittest.mock import Mock
from zipfile import ZipFile

import pytest
from bs4 import BeautifulSoup
from pypdf import PdfReader

import app.topic as topic_module
from app.archive import ArchiveService
from app.config import Settings
from app.fetcher import FetchError, PageSnapshot
from app.parser import ArticleParser, ParsedArticle
from app.models import ArticleMetadata
from app.outputs import OutputError
from app.resources import ResourceDownloadResult
from app.topic import TopicFailure, TopicProgress, TopicService
from app.topic_history import read_topic_archive


TOPIC_URL = "https://blog.csdn.net/demo/topic"
ARTICLE_ONE = "https://blog.csdn.net/demo/article/details/1"
ARTICLE_TWO = "https://blog.csdn.net/demo/article/details/2"


@pytest.fixture(autouse=True)
def skip_topic_batch_delays(monkeypatch):
    monkeypatch.setattr(topic_module, "sleep", Mock())


class FakeFetcher:
    def __init__(self, failed: str | None = None):
        self.failed = failed

    def fetch(self, url: str, *, referer: str | None = None) -> PageSnapshot:
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
    archive_service = ArchiveService(Settings.from_project_root(tmp_path))
    archive_service.fetcher = FakeFetcher(failed)
    archive_service.parser = FakeParser()
    archive_service.resources = FakeResources()
    return TopicService(archive_service)


def test_discover_topic_links_preserves_order_and_deduplicates() -> None:
    title, urls = TopicService.discover(
        f"<html><head><meta property='og:title' content='专题标题'></head><body><a href='{ARTICLE_TWO}'>2</a><a href='{ARTICLE_ONE}'>1</a><a href='{ARTICLE_TWO}'>重复</a><a href='https://example.com/article/details/3'>外部</a></body></html>",
        TOPIC_URL,
    )

    assert title == "专题标题"
    assert urls == [ARTICLE_TWO, ARTICLE_ONE]


def test_discover_column_ignores_sidebar_articles() -> None:
    column_url = "https://blog.csdn.net/demo/category_123.html"
    unrelated = "https://blog.csdn.net/demo/article/details/999"
    html = f"""
    <title>页面标题</title>
    <aside><a href="{unrelated}">热门文章</a></aside>
    <main id="column">
      <h3 class="column_title">实际专栏标题</h3>
      <ul class="column_article_list">
        <li><a href="{ARTICLE_TWO}">目录第一篇</a></li>
        <li><a href="{ARTICLE_ONE}">目录第二篇</a></li>
        <li><a href="{ARTICLE_TWO}#section">重复链接</a></li>
      </ul>
    </main>
    """

    assert TopicService.discover(html, column_url) == ("实际专栏标题", [ARTICLE_TWO, ARTICLE_ONE])


def test_discover_column_without_article_list_does_not_use_sidebar() -> None:
    url = "https://blog.csdn.net/demo/category_123_2.html"
    html = f'<aside><a href="{ARTICLE_ONE}">热门文章</a></aside>'

    assert TopicService.discover(html, url)[1] == []


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


def test_redownloading_topic_keeps_its_folder_when_title_changes(monkeypatch, tmp_path: Path) -> None:
    service = make_service(tmp_path)
    url = "https://blog.csdn.net/demo/category_123.html"
    title = "原专题"
    monkeypatch.setattr(service, "discover", lambda *_: (title, [ARTICLE_ONE, ARTICLE_TWO]))
    first = service.download(url, article_limit=2)
    title = "更新后的专题"
    updated = service.download(url, article_limit=2)
    epub = service.download(url, "epub", article_limit=2)
    assert updated.output_path == first.output_path
    assert updated.output_path.relative_to(service.archive_service.settings.data_dir).as_posix() == (
        "topics/123_原专题/前2篇/html/topic.html"
    )
    assert epub.output_path.parent.parent == updated.output_path.parent.parent
    assert "更新后的专题" in updated.output_path.read_text(encoding="utf-8")


def test_single_and_topic_share_article_preparation(monkeypatch, tmp_path: Path) -> None:
    topic_service = make_service(tmp_path)
    archive_service = topic_service.archive_service
    prepare = Mock(wraps=archive_service.prepare_article)
    monkeypatch.setattr(archive_service, "prepare_article", prepare)

    single = archive_service.archive(ARTICLE_ONE)
    topic = topic_service.download(TOPIC_URL, concurrency=2)

    assert prepare.call_args_list[0].args[0] == ARTICLE_ONE
    topic_calls = [call.args for call in prepare.call_args_list[1:]]
    assert sorted(url for url, _ in topic_calls) == [ARTICLE_ONE, ARTICLE_TWO]
    assert {call.kwargs["referer"] for call in prepare.call_args_list[1:]} == {TOPIC_URL}
    assert len({assets_dir for _, assets_dir in topic_calls}) == 2
    assert [article.title for article in topic.articles] == ["文章 1", "文章 2"]
    assert [item["title"] for item in archive_service.index.list_all()] == ["文章 1"]
    assert list(single.paths.archive_dir.parent.glob("*/article.html")) == [single.paths.html]


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


@pytest.mark.parametrize("output_format", ["html", "epub", "pdf", "md"])
def test_topic_export_labels_the_topic_and_article_urls(tmp_path: Path, output_format: str) -> None:
    service = make_service(tmp_path, ARTICLE_TWO)

    result = service.download(TOPIC_URL, output_format)

    if output_format == "pdf":
        pages = PdfReader(result.output_path).pages
        text = "".join("".join(page.extract_text().split()) for page in pages)
        links = {link.get_object().get("/A", {}).get("/URI") for page in pages for link in page.get("/Annots", [])}
        for url in (TOPIC_URL, ARTICLE_ONE, ARTICLE_TWO):
            assert url in text
            assert url in links
    elif output_format == "md":
        text = result.output_path.read_text(encoding="utf-8")
        for url in (TOPIC_URL, ARTICLE_ONE, ARTICLE_TWO):
            assert f"原始 URL：[{url}]({url})" in text
        assert "下载失败：文章访问失败" in text
    else:
        if output_format == "epub":
            with ZipFile(result.output_path) as book:
                text = book.read("OEBPS/content.xhtml").decode("utf-8")
        else:
            text = result.output_path.read_text(encoding="utf-8")
        document = BeautifulSoup(text, "lxml")
        assert document.select_one("h1 + p a")["href"] == TOPIC_URL
        assert document.select_one("#article-1 h2 + p a")["href"] == ARTICLE_ONE
        assert document.select_one("nav li:nth-child(2) a")["href"] == ARTICLE_TWO


def test_parallel_progress_reports_completed_articles_before_sorting(monkeypatch, tmp_path: Path) -> None:
    service = make_service(tmp_path, ARTICLE_TWO)
    download_article = service._download_article
    first_completion_reported = Event()
    updates = []

    def download_with_slow_first(position, url, work_root, saved_html=None, *, referer=None):
        if position == 1:
            assert first_completion_reported.wait(timeout=3)
        return download_article(position, url, work_root, saved_html, referer=referer)

    def report(progress: TopicProgress) -> None:
        updates.append(progress)
        if progress.processed == 1:
            first_completion_reported.set()

    monkeypatch.setattr(service, "_download_article", download_with_slow_first)
    result = service.download(TOPIC_URL, concurrency=2, on_progress=report)

    assert updates == [
        TopicProgress("downloading", 2, discovered_total=2),
        TopicProgress("downloading", 2, 1, 1, 2),
        TopicProgress("downloading", 2, 2, 1, 2),
        TopicProgress("exporting", 2, 2, 1, 2),
    ]
    assert [article.url for article in result.articles] == [ARTICLE_ONE, ARTICLE_TWO]


def test_topic_preview_downloads_first_five_without_overwriting_full_export(monkeypatch, tmp_path: Path) -> None:
    urls = [ARTICLE_TWO, ARTICLE_ONE] + [
        f"https://blog.csdn.net/demo/article/details/{number}" for number in range(3, 7)
    ]
    monkeypatch.setattr(TopicService, "discover", staticmethod(lambda *_: ("测试专题", urls)))

    monkeypatch.setenv("CSDN2LOCAL_TOPIC_ARTICLE_LIMIT", "0")
    full = make_service(tmp_path).download(TOPIC_URL)
    full_html = full.output_path.read_bytes()

    monkeypatch.delenv("CSDN2LOCAL_TOPIC_ARTICLE_LIMIT")
    preview_service = make_service(tmp_path)
    fetcher = preview_service.archive_service.fetcher
    fetch = Mock(wraps=fetcher.fetch)
    monkeypatch.setattr(fetcher, "fetch", fetch)
    updates = []
    preview = preview_service.download(TOPIC_URL, on_progress=updates.append)

    assert [article.url for article in full.articles] == urls
    assert [article.url for article in preview.articles] == urls[:5]
    assert [call.args[0] for call in fetch.call_args_list] == [TOPIC_URL, *urls[:5]]
    assert updates[-1] == TopicProgress("exporting", 5, 5, 0, 6)
    assert preview.output_path != full.output_path
    assert full.output_path.read_bytes() == full_html
    metadata = json.loads(preview.metadata_path.read_text(encoding="utf-8"))
    assert metadata["article_limit"] == 5
    assert metadata["discovered_article_count"] == 6

    epub = preview_service.download(TOPIC_URL, "epub", article_limit=0)
    assert [article.url for article in epub.articles] == urls
    assert epub.output_path.is_file()
    assert full.output_path.read_bytes() == full_html


def test_topic_download_generates_selected_pdf(monkeypatch, tmp_path: Path) -> None:
    service = make_service(tmp_path)

    def fake_write_pdf(html_path: Path, pdf_path: Path) -> None:
        assert html_path.exists()
        pdf_path.write_bytes(b"%PDF-topic")

    monkeypatch.setattr(topic_module, "write_pdf", fake_write_pdf)
    result = service.download(TOPIC_URL, "pdf", 1)

    assert result.output_path.name == "topic.pdf"
    assert result.output_path.read_bytes().startswith(b"%PDF")


def test_topic_retry_rebuilds_pdf_from_saved_bodies_and_preserves_previous_file_on_export_error(
    monkeypatch, tmp_path: Path
) -> None:
    service = make_service(tmp_path, ARTICLE_TWO)
    fetcher = service.archive_service.fetcher
    fetch = Mock(wraps=fetcher.fetch)
    monkeypatch.setattr(fetcher, "fetch", fetch)
    rendered = []

    def write_pdf(html_path: Path, pdf_path: Path) -> None:
        rendered.append(html_path.read_text(encoding="utf-8"))
        if len(rendered) == 2:
            raise OutputError("生成失败")
        pdf_path.write_bytes(f"%PDF-{len(rendered)}".encode())

    monkeypatch.setattr(topic_module, "write_pdf", write_pdf)
    result = service.download(TOPIC_URL, "pdf")
    record = read_topic_archive(result.output_path.parent)
    assert record and record.can_retry
    fetcher.failed = None
    fetch.reset_mock()

    with pytest.raises(TopicFailure, match="生成失败") as failed:
        service.retry_article(record.attempt, 2, on_progress=lambda _: None)
    assert failed.value.attempt is not None
    assert result.output_path.read_bytes() == b"%PDF-1"
    assert "正文 1" in rendered[0] and "正文 2" not in rendered[0]

    repaired = service.retry_article(record.attempt, 2, on_progress=lambda _: None)
    assert repaired.status == "success"
    assert repaired.output_path.read_bytes() == b"%PDF-3"
    assert rendered[-1].index("正文 1") < rendered[-1].index("正文 2")
    assert [call.args[0] for call in fetch.call_args_list] == [ARTICLE_TWO, ARTICLE_TWO]


@pytest.mark.skipif(sys.platform != "win32", reason="Requires Windows directory sharing rules")
def test_topic_retry_publishes_epub_while_staged_file_is_open(monkeypatch, tmp_path: Path) -> None:
    service = make_service(tmp_path, ARTICLE_TWO)
    result = service.download(TOPIC_URL, "epub")
    store = service.archive_service.store
    legacy = store.settings.data_dir / "blog.csdn.net" / "topics" / "preview-5-epub-专题"
    legacy.parent.mkdir(parents=True)
    result.output_path.parent.replace(legacy)
    (legacy / TopicService.BODY_CACHE).unlink()
    record = read_topic_archive(legacy)
    assert record and record.can_retry
    service.archive_service.fetcher.failed = None
    fetch = Mock(wraps=service.archive_service.fetcher.fetch)
    monkeypatch.setattr(service.archive_service.fetcher, "fetch", fetch)
    commit = store.commit

    def commit_with_open_epub(staging, target):
        with (staging.archive_dir / "topic.epub").open("rb"):
            commit(staging, target)

    monkeypatch.setattr(store, "commit", commit_with_open_epub)

    repaired = service.retry_article(record.attempt, 2, on_progress=lambda _: None)

    assert repaired.status == "success"
    assert repaired.output_path == legacy / "topic.epub"
    with ZipFile(repaired.output_path) as book:
        content = book.read("OEBPS/content.xhtml").decode("utf-8")
        assert content.index("正文 1") < content.index("正文 2")
        document = BeautifulSoup(content, "lxml")
        for position, url in enumerate((ARTICLE_ONE, ARTICLE_TWO), 1):
            assert [link["href"] for link in document.select(f"#article-{position} a")] == [url]
    assert [call.args[0] for call in fetch.call_args_list] == [ARTICLE_TWO]
    assert list(store.staging_root.iterdir()) == []


def test_topic_waits_one_second_between_completed_batches(monkeypatch, tmp_path: Path) -> None:
    service = make_service(tmp_path)
    urls = [f"https://blog.csdn.net/demo/article/details/{number}" for number in range(1, 6)]
    monkeypatch.setattr(service, "discover", lambda *_: ("测试专题", urls))
    started = []
    updates = []
    pauses = []
    download_article = service._download_article

    def download(position, url, work_root, saved_html=None, *, referer=None):
        started.append(position)
        return download_article(position, url, work_root, saved_html, referer=referer)

    def pause(seconds):
        pauses.append((seconds, updates[-1].processed, set(started)))

    monkeypatch.setattr(service, "_download_article", download)
    monkeypatch.setattr(topic_module, "sleep", pause)
    result = service.download(TOPIC_URL, concurrency=2, on_progress=updates.append)

    assert pauses == [(1, 2, {1, 2}), (1, 4, {1, 2, 3, 4})]
    assert [article.url for article in result.articles] == urls


def test_topic_output_and_concurrency_validation() -> None:
    assert TopicService.normalize_output_format("EPUB") == "epub"
    assert TopicService.normalize_concurrency("1") == 1
    with pytest.raises(ValueError):
        TopicService.normalize_output_format("html,pdf")
    with pytest.raises(ValueError):
        TopicService.normalize_concurrency(0)


def test_topic_exports_browser_saved_articles_when_online_pages_are_blocked(monkeypatch, tmp_path: Path) -> None:
    service = make_service(tmp_path)
    service.archive_service.parser = ArticleParser()
    fetch_topic = service.archive_service.fetcher.fetch

    def fetch(url, *, referer=None):
        if url != TOPIC_URL:
            raise FetchError("CSDN 安全防护拦截（HTTP 521）")
        return fetch_topic(url)

    fetch_page = Mock(side_effect=fetch)
    monkeypatch.setattr(service.archive_service.fetcher, "fetch", fetch_page)

    with pytest.raises(TopicFailure) as failed:
        service.download(TOPIC_URL)
    assert [article.url for article in failed.value.articles] == [ARTICLE_ONE, ARTICLE_TWO]

    fetch_page.reset_mock()
    result = service.download(
        TOPIC_URL,
        saved_articles={
            "2": f'<link rel="canonical" href="{ARTICLE_TWO}"><title>本地第二篇</title><div id="content_views">第二篇正文</div>',
            "1": f'<link rel="canonical" href="{ARTICLE_ONE}"><title>本地第一篇</title><div id="content_views">第一篇正文<script>不保留的脚本</script></div>',
        },
    )

    fetch_page.assert_called_once_with(TOPIC_URL)
    assert result.status == "success"
    assert [article.source for article in result.articles] == ["saved_html", "saved_html"]
    output = result.output_path.read_text(encoding="utf-8")
    assert output.index("第一篇正文") < output.index("第二篇正文")
    assert "不保留的脚本" not in output


def test_topic_rejects_saved_html_for_a_different_article(tmp_path: Path) -> None:
    service = make_service(tmp_path, ARTICLE_TWO)
    service.archive_service.parser = ArticleParser()

    with pytest.raises(TopicFailure, match="原文地址与文件名中的文章 ID 不一致"):
        service.download(
            TOPIC_URL,
            saved_articles={"1": f'<link rel="canonical" href="{ARTICLE_TWO}"><div id="content_views">正文</div>'},
        )
