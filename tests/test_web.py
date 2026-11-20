from __future__ import annotations

import asyncio
import json
import os
import shutil
from io import BytesIO
from pathlib import Path
from threading import Event
from zipfile import ZipFile

import httpx
import pytest
import respx
from bs4 import BeautifulSoup

import app.main as main
import app.topic as topic_module
from app.archive import ArchiveResult, ArchiveService
from app.config import Settings
from app.fetcher import FetchError, PageSnapshot
from app.models import ArticleMetadata
from app.storage import ArchivePaths
from app.topic import TopicArticle, TopicFailure, TopicProgress, TopicResult, TopicService
from app.topic_jobs import TopicJobs
from app.topic_outputs import write_topic_epub


class FakeIndex:
    def __init__(self, result):
        self.result = result

    def search(self, keyword: str):
        return self.result if keyword == "python" else []

    def list_all(self):
        return self.result


class FakeService:
    def __init__(self, result):
        self.index = FakeIndex([])
        self.result = result
        self.calls = []

    def archive(self, url: str, formats: list[str]):
        self.calls.append((url, formats))
        return self.result


class FakeTopicService:
    def __init__(self, result):
        self.result = result
        self.calls = []
        self.started = Event()
        self.release = Event()
        self.saved_articles = None
        self.article_limit = None

    def download(self, url: str, output_format: str, concurrency: int, *, article_limit, on_progress, saved_articles=None):
        self.calls.append((url, output_format, concurrency))
        self.article_limit = article_limit
        self.saved_articles = saved_articles
        on_progress(TopicProgress("downloading", total=2, processed=1, failed=1, discovered_total=3))
        self.started.set()
        assert self.release.wait(timeout=5), "Test did not release topic download"
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


@pytest.mark.asyncio
async def test_search_displays_only_title_and_local_address(monkeypatch, tmp_path: Path) -> None:
    archive = tmp_path / "blog.csdn.net" / "article"
    archive.mkdir(parents=True)
    html = archive / "article.html"
    html.write_text("<html>offline</html>", encoding="utf-8")
    fake = FakeService(None)
    fake.index = FakeIndex(
        [
            {"title": "Python title", "address": str(html), "original_url": "https://blog.csdn.net/a"},
        ]
    )
    monkeypatch.setattr(main, "archive_service", fake)
    monkeypatch.setattr(main, "_file_url", lambda path: "/files/test/article.html")

    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/?q=python")

    assert response.status_code == 200
    assert "Python title" in response.text
    assert "/files/test/article.html" in response.text
    assert "https://blog.csdn.net/a" not in response.text


@pytest.mark.asyncio
async def test_home_displays_downloaded_file_list_without_keyword(monkeypatch, tmp_path: Path) -> None:
    archive = tmp_path / "blog.csdn.net" / "article"
    archive.mkdir(parents=True)
    html = archive / "article.html"
    html.write_text("<html>offline</html>", encoding="utf-8")
    fake = FakeService(None)
    fake.index = FakeIndex(
        [
            {"title": "Downloaded title", "address": str(html), "original_url": "https://blog.csdn.net/a"},
        ]
    )
    monkeypatch.setattr(main, "archive_service", fake)
    monkeypatch.setattr(main, "_file_url", lambda path: "/files/test/article.html")

    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/")

    assert response.status_code == 200
    assert "单篇下载记录" in response.text
    assert "Downloaded title" in response.text
    assert "/files/test/article.html" in response.text
    assert "https://blog.csdn.net/a" not in response.text


@pytest.mark.asyncio
async def test_single_history_filters_available_files_and_search(monkeypatch, tmp_path: Path) -> None:
    settings = Settings.from_project_root(tmp_path)
    service = ArchiveService(settings)
    monkeypatch.setattr(main, "settings", settings)
    monkeypatch.setattr(main, "archive_service", service)
    for slug, title, formats in [
        ("mixed", "Python 多格式", ("html", "pdf", "md")),
        ("html", "Python 网页", ("html",)),
        ("pdf", "Go 文档", ("pdf",)),
    ]:
        paths = ArchivePaths(settings.data_dir / "articles" / slug)
        paths.archive_dir.mkdir(parents=True)
        for fmt in formats:
            getattr(paths, fmt).write_text(fmt, encoding="utf-8")
        service.index.upsert(
            ArticleMetadata(title, f"https://blog.csdn.net/demo/{slug}", "blog.csdn.net"),
            paths,
        )

    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/", params={"q": "Python", "history_format": "pdf"})
        page = BeautifulSoup(response.text, "lxml")
        rows = page.select("#library li")
        assert len(rows) == 1
        title = rows[0].select_one(".result-title")
        assert title.get_text(strip=True) == "Python 多格式"
        assert title["href"].endswith("/mixed/article.pdf")
        assert [a["href"] for a in rows[0].select(".history-meta a")] == [title["href"]]
        assert page.select_one('#library select option[selected]')["value"] == "pdf"

        cleared = await client.get(page.select_one("#library .hint a")["href"])
        cleared_page = BeautifulSoup(cleared.text, "lxml")
        assert {a.get_text(strip=True) for a in cleared_page.select("#library .result-title")} == {
            "Python 多格式", "Go 文档",
        }
        assert cleared_page.select_one('#library select option[selected]')["value"] == "pdf"

        markdown = BeautifulSoup((await client.get("/?history_format=md")).text, "lxml")
        assert markdown.select_one("#library .result-title")["href"].endswith("/mixed/article.md?bundle=1")
        for value in ("", "epub"):
            all_types = BeautifulSoup((await client.get(
                "/", params={"q": "Python", "history_format": value},
            )).text, "lxml")
            assert len(all_types.select("#library li")) == 2
            assert all_types.select_one('#library select option[selected]')["value"] == ""

        empty = await client.get("/", params={"q": "Go", "history_format": "html"})
        assert "没有找到匹配的文章" in empty.text


@pytest.mark.asyncio
async def test_home_displays_empty_state_without_downloads(monkeypatch) -> None:
    fake = FakeService(None)
    fake.index = FakeIndex([])
    monkeypatch.setattr(main, "archive_service", fake)

    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/")

    assert response.status_code == 200
    assert "这里还没有文章" in response.text
    assert "class=\"primary-task\"" in response.text
    assert "开始保存" in response.text
    assert "保存之后" not in response.text


@pytest.mark.asyncio
async def test_archive_form_defaults_to_html_and_can_retry(monkeypatch, tmp_path: Path) -> None:
    archive = tmp_path / "blog.csdn.net" / "article"
    archive.mkdir(parents=True)
    html = archive / "article.html"
    html.write_text("<html>offline</html>", encoding="utf-8")
    metadata = ArticleMetadata(title="Saved", original_url="https://blog.csdn.net/a", domain="blog.csdn.net", formats=["html"])
    result = ArchiveResult("success", metadata, ArchivePaths(archive))
    fake = FakeService(result)
    monkeypatch.setattr(main, "archive_service", fake)
    monkeypatch.setattr(main, "_file_url", lambda path: "/files/test/article.html")

    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post("/archive", data={"url": "https://blog.csdn.net/a"})

    assert response.status_code == 200
    assert "文章保存完成" in response.text
    assert fake.calls == [("https://blog.csdn.net/a", ["html"])]
    shutil.rmtree(tmp_path, ignore_errors=True)


@pytest.mark.asyncio
async def test_single_failure_edit_restores_url_and_selected_format(monkeypatch) -> None:
    source = "https://blog.csdn.net/demo/article/details/123"

    def fail(*args):
        raise FetchError("读取超时")

    monkeypatch.setattr(main, "archive_service", FakeService(None))
    monkeypatch.setattr(main.archive_service, "archive", fail)
    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        failed = await client.post("/archive", data={"url": source, "formats": "pdf"})
        assert failed.status_code == 400
        page = BeautifulSoup(failed.text, "lxml")
        edit_link = page.find("a", string="修改设置")
        assert edit_link is not None
        form = BeautifulSoup((await client.get(edit_link["href"])).text, "lxml")
        assert form.select_one('input[name="url"]')["value"] == source
        assert [field["value"] for field in form.select('input[name="formats"][type="radio"]')] == ["html", "pdf", "md"]
        assert [field["value"] for field in form.select('input[name="formats"][checked]')] == ["pdf"]
        assert "首次导出 PDF 时会自动下载 Chromium" in form.select_one("#pdf-runtime-help").get_text()


@pytest.mark.asyncio
async def test_topic_page_has_navigation_single_format_and_default_concurrency(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(main, "settings", Settings.from_project_root(tmp_path))
    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/topic")

    assert response.status_code == 200
    assert "单篇下载" in response.text
    assert "专题下载" in response.text
    assert 'name="concurrency"' in response.text
    assert 'value="1"' in response.text
    page = BeautifulSoup(response.text, "lxml")
    assert [field["value"] for field in page.select('input[type="radio"][name="output_format"]')] == [
        "html", "epub", "pdf", "md",
    ]
    assert [field["value"] for field in page.select('input[name="output_format"][checked]')] == ["html"]
    assert "首次导出 PDF 时会自动下载 Chromium" in page.select_one("#pdf-runtime-help").get_text()
    assert "暂无专题下载记录" in response.text
    assert page.select_one('input[name="article_limit"]')["value"] == "5"
    assert [item["data-article-limit"] for item in page.select("[data-article-limit]")] == ["5", "10", "0"]


@pytest.mark.asyncio
async def test_topic_page_opens_saved_archives_without_a_job(monkeypatch, tmp_path: Path) -> None:
    settings = Settings.from_project_root(tmp_path)
    monkeypatch.setattr(main, "settings", settings)
    monkeypatch.setattr(main, "topic_jobs", TopicJobs())
    topics = settings.data_dir / "blog.csdn.net" / "topics"
    for name, title, fmt, timestamp in [
        ("topic-旧归档", "旧版专题", "epub", 1700000000),
        ("preview-5-topic-新归档", "最新试下载", "html", 1700000100),
        ("topic-已移除", "已移除的文件", "html", None),
        (".topic-backup", "临时备份", "html", 1700000200),
    ]:
        directory = topics / name
        directory.mkdir(parents=True)
        (directory / "metadata.json").write_text(
            json.dumps({
                "title": title, "format": fmt,
                "original_url": "https://blog.csdn.net/demo/category_123.html",
            }), encoding="utf-8"
        )
        if timestamp is not None:
            output = directory / f"topic.{fmt}"
            output.write_text(f"本地归档：{title}", encoding="utf-8")
            os.utime(output, (timestamp, timestamp))
    bad_metadata = topics / "topic-损坏"
    bad_metadata.mkdir()
    (bad_metadata / "metadata.json").write_text("{", encoding="utf-8")
    (bad_metadata / "topic.html").write_text("invalid", encoding="utf-8")

    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/topic")
        assert response.status_code == 200
        page = BeautifulSoup(response.text, "lxml")
        links = page.select("#topic-history a.result-title")
        assert [link.get_text(strip=True) for link in links] == ["最新试下载"]
        listed_versions = page.select("#topic-history .result-list > li > ul > li > a")
        assert [link.get_text().strip().split(" · ")[:2] for link in listed_versions] == [
            ["HTML", "前 5 篇"], ["EPUB", "全部"],
        ]
        assert all(link.select_one("time[datetime]") for link in listed_versions)
        detail = BeautifulSoup((await client.get(links[0]["href"])).text, "lxml")
        versions = detail.select(".version-list a")
        assert len(versions) == 2
        assert "HTML · 前 5 篇" in versions[0].get_text()
        assert "EPUB · 全部" in versions[1].get_text()
        assert [link["href"] for link in listed_versions] == [link["href"] for link in versions]
        for link, expected_title in zip(versions, ["最新试下载", "旧版专题"], strict=True):
            version = BeautifulSoup((await client.get(link["href"])).text, "lxml")
            assert version.select_one("h1").get_text(strip=True) == expected_title
            local = await client.get(version.select_one(".output-links a")["href"])
            assert local.status_code == 200
            assert local.content.decode("utf-8") == f"本地归档：{expected_title}"


@pytest.mark.asyncio
async def test_topic_history_filters_versions_before_sorting_groups(monkeypatch, tmp_path: Path) -> None:
    settings = Settings.from_project_root(tmp_path)
    monkeypatch.setattr(main, "settings", settings)
    monkeypatch.setattr(main, "topic_jobs", TopicJobs())
    root = settings.data_dir / "blog.csdn.net" / "topics"
    for name, topic_id, fmt, timestamp in [
        ("第一专题网页", 1, "html", 1700000400),
        ("第二专题 EPUB", 2, "epub", 1700000300),
        ("第一专题 EPUB", 1, "epub", 1700000200),
        ("preview-5-第一专题 EPUB", 1, "epub", 1700000100),
        ("第三专题网页", 3, "html", 1700000000),
    ]:
        archive_dir = root / name
        archive_dir.mkdir(parents=True)
        (archive_dir / "metadata.json").write_text(json.dumps({
            "title": name,
            "format": fmt,
            "original_url": f"https://blog.csdn.net/demo/category_{topic_id}.html",
        }), encoding="utf-8")
        output = archive_dir / f"topic.{fmt}"
        output.touch()
        os.utime(output, (timestamp, timestamp))

    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        page = BeautifulSoup((await client.get("/topic?history_format=epub")).text, "lxml")
        titles = page.select("#topic-history .result-title")
        assert [title.get_text(strip=True) for title in titles] == ["第二专题 EPUB", "第一专题 EPUB"]
        links = page.select("#topic-history .result-list > li > ul > li > a")
        assert [link.get_text(" ", strip=True).split(" · ")[:2] for link in links] == [
            ["EPUB", "全部"], ["EPUB", "全部"], ["EPUB", "前 5 篇"],
        ]
        assert [title["href"] for title in titles] == [links[0]["href"], links[1]["href"]]
        assert page.select_one('#topic-history select option[selected]')["value"] == "epub"

        empty = await client.get("/topic?history_format=pdf")
        assert "没有找到匹配的专题下载记录" in empty.text


@pytest.mark.asyncio
@pytest.mark.parametrize("output_format", ["pdf", "epub", "md"])
async def test_topic_form_submits_single_format_and_concurrency(monkeypatch, tmp_path: Path, output_format: str) -> None:
    settings = Settings.from_project_root(tmp_path)
    archive_dir = settings.data_dir / "topics" / "example" / "all" / output_format
    archive_dir.mkdir(parents=True)
    output = archive_dir / f"topic.{output_format}"
    output.write_bytes(b"topic")
    result = TopicResult(
        status="partial",
        topic_title="测试专题",
        topic_url="https://blog.csdn.net/demo/topic",
        output_format=output_format,
        output_path=output,
        metadata_path=archive_dir / "metadata.json",
        articles=[TopicArticle(position=1, url="https://blog.csdn.net/demo/article/details/1", title="文章一")],
    )
    result.metadata_path.write_text(json.dumps({
        "title": result.topic_title,
        "original_url": result.topic_url,
        "format": output_format,
        "articles": [{"position": 1, "url": result.articles[0].url, "title": result.articles[0].title}],
    }), encoding="utf-8")
    (archive_dir / "assets").mkdir()
    image = archive_dir / "assets" / "image.png"
    image.write_bytes(b"local image")
    body = '<p>第一篇本地正文</p><img src="assets/image.png">'
    if output_format == "epub":
        write_topic_epub(output, result.topic_title, [{**result.articles[0].as_dict(), "body_html": body}], [image])
    else:
        (archive_dir / TopicService.BODY_CACHE).write_text(json.dumps({"1": body}), encoding="utf-8")
    fake = FakeTopicService(result)
    monkeypatch.setattr(main, "settings", settings)
    monkeypatch.setattr(main, "topic_service", fake)
    monkeypatch.setattr(main, "topic_jobs", TopicJobs())
    form = {"topic_url": result.topic_url, "output_format": output_format, "concurrency": "3", "article_limit": "0"}

    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        try:
            invalid = await client.post("/topic", data={**form, "output_format": ["html", output_format]})
            assert invalid.status_code == 400
            assert not fake.calls
            submission = await client.post("/topic", data=form)
            assert submission.status_code == 303
            job_url = submission.headers["location"]
            assert await asyncio.to_thread(fake.started.wait, 3)
            progress = await client.get(job_url)
            assert progress.status_code == 200
            assert progress.headers["Cache-Control"] == "no-store"
            assert "正在下载文章" in progress.text
            steps = BeautifulSoup(progress.text, "lxml").select("[data-stage-step]")
            assert [step["data-stage-step"] for step in steps] == ["discovering", "downloading", "exporting"]
            assert [step["data-stage-step"] for step in steps if step.get("aria-current") == "step"] == ["downloading"]
            assert ("自动下载 Chromium" in progress.text) == (output_format == "pdf")
            assert "1 / 2" in progress.text
            assert "失败文章" in progress.text
            assert "专题共 3 篇，本次只处理前 2 篇" in progress.text
            assert 'http-equiv="refresh" content="2"' in progress.text
            status = await client.get(f"{job_url}/status")
            assert status.headers["Cache-Control"] == "no-store"
            assert status.json()["processed"] == 1
            assert status.json()["finished"] is False
            assert job_url in (await client.get("/topic")).text

            busy = await client.post("/topic", data=form)
            assert busy.status_code == 409
            assert job_url in busy.text
        finally:
            fake.release.set()
        response = await wait_for_topic_result(client, job_url)
        assert (await client.get(f"{job_url}/status")).json()["finished"] is True
        page = BeautifulSoup(response.text, "lxml")
        edit_link = page.find("a", string="修改设置")
        assert edit_link is not None
        edited = BeautifulSoup((await client.get(edit_link["href"])).text, "lxml")
        assert edited.select_one('input[name="topic_url"]')["value"] == result.topic_url
        assert edited.select_one('input[name="output_format"][checked]')["value"] == output_format
        assert edited.select_one('input[name="concurrency"]')["value"] == "3"
        assert edited.select_one('input[name="article_limit"]')["value"] == "0"
        history = await client.get(f"/topic/history/topics/example/all/{output_format}")
        assert history.status_code == 200
        file_url = f"/files/topics/example/all/{output_format}/topic.{output_format}"
        expected_title_url = file_url + ("#nameddest=article-1" if output_format == "pdf" else "?article=1")
        for document in (page, BeautifulSoup(history.text, "lxml")):
            title = document.select_one("a.article-result-title")
            assert title is not None
            assert title["href"] == expected_title_url
        local = await client.get(expected_title_url)
        assert local.status_code == 200
        if output_format != "pdf":
            article = BeautifulSoup(local.text, "lxml").select_one("article")
            assert article.h1.get_text() == "文章一"
            assert "第一篇本地正文" in article.get_text()
            assert article.img["src"] == "assets/image.png"
            assert (await client.get(file_url.rsplit("/", 1)[0] + "/assets/image.png")).content == b"local image"
            assert (await client.get(file_url, params={"article": 99})).status_code == 404

    assert response.status_code == 200
    assert "测试专题" in response.text
    assert f"/files/topics/example/all/{output_format}/topic.{output_format}" in response.text
    assert "重新下载专题" in response.text
    assert f'name="output_format" value="{output_format}"' in response.text
    assert 'name="concurrency" value="3"' in response.text
    assert 'name="article_limit" value="0"' in response.text
    assert "专题共 3 篇，本次只处理前 2 篇" in response.text
    assert 'http-equiv="refresh"' not in response.text
    assert fake.calls == [(result.topic_url, output_format, 3)]
    assert fake.article_limit == 0


@pytest.mark.asyncio
async def test_topic_progress_displays_failure_and_retry(monkeypatch) -> None:
    article_url = "https://blog.csdn.net/demo/article/details/123"
    fake = FakeTopicService(TopicFailure("专题读取失败", [TopicArticle(1, article_url, error="HTTP 521")]))
    fake.release.set()
    monkeypatch.setattr(main, "topic_service", fake)
    monkeypatch.setattr(main, "topic_jobs", TopicJobs())
    topic_url = "https://blog.csdn.net/demo/topic"

    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        submission = await client.post("/topic", data={"topic_url": topic_url})
        response = await wait_for_topic_result(client, submission.headers["location"])
        missing = await client.get("/topic/jobs/unknown")

    assert "专题读取失败" in response.text
    assert "重新下载" in response.text
    assert f'href="{article_url}"' in response.text
    assert 'name="article_html"' in response.text
    assert topic_url in response.text
    assert missing.status_code == 404
    assert "返回专题配置" in missing.text
    assert fake.calls == [(topic_url, "html", 1)]


@pytest.mark.asyncio
async def test_topic_submit_passes_saved_html_to_background_job(monkeypatch) -> None:
    fake = FakeTopicService(TopicFailure("测试结束"))
    fake.release.set()
    monkeypatch.setattr(main, "topic_service", fake)
    monkeypatch.setattr(main, "topic_jobs", TopicJobs())
    source = "<div id='content_views'>用户另存的正文</div>"
    form = {"topic_url": "https://blog.csdn.net/demo/topic"}

    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post("/topic", data=form, files={"article_html": ("123.html", source.encode())})
        assert response.status_code == 303
        await wait_for_topic_result(client, response.headers["location"])
        invalid = await client.post("/topic", data=form, files={"article_html": ("unknown.html", b"<p>x</p>")})

    assert fake.saved_articles == {"123": source}
    assert invalid.status_code == 400
    assert "请用文章 ID" in invalid.text


@pytest.mark.asyncio
async def test_topic_retry_form_imports_saved_articles_and_serves_ordered_html(monkeypatch, tmp_path: Path) -> None:
    topic_url = "https://blog.csdn.net/demo/category_123.html"
    article_one = "https://blog.csdn.net/demo/article/details/11"
    article_two = "https://blog.csdn.net/demo/article/details/22"
    settings = Settings.from_project_root(tmp_path)
    service = TopicService(ArchiveService(settings))
    requests = []

    def fetch(url: str, *, referer: str | None = None) -> PageSnapshot:
        requests.append(url)
        if url != topic_url:
            raise FetchError("CSDN 安全防护拦截（HTTP 521）")
        return PageSnapshot(
            url, url,
            f'<div id="column"><ul class="column_article_list">'
            f'<li><a href="{article_one}">目录第一篇</a></li>'
            f'<li><a href="{article_two}">目录第二篇</a></li></ul></div>',
        )

    monkeypatch.setattr(main, "settings", settings)
    monkeypatch.setattr(main, "topic_service", service)
    monkeypatch.setattr(main, "topic_jobs", TopicJobs())
    monkeypatch.setattr(service.archive_service.fetcher, "fetch", fetch)
    monkeypatch.setattr(topic_module, "sleep", lambda _: None)

    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        submission = await client.post("/topic", data={"topic_url": topic_url})
        assert submission.status_code == 303
        failed = await wait_for_topic_result(client, submission.headers["location"])
        page = BeautifulSoup(failed.text, "lxml")
        assert not page.select("a.article-result-title")
        assert [link["href"] for link in page.select(".article-result-status a")] == [article_one, article_two]
        retry_form = page.select_one('form[action="/topic"][enctype="multipart/form-data"]')
        assert retry_form is not None
        assert retry_form.select_one('input[name="article_html"][multiple]') is not None
        form_data = {item["name"]: item["value"] for item in retry_form.select('input[type="hidden"]')}

        retried = await client.post(
            retry_form["action"],
            data=form_data,
            files=[
                ("article_html", ("22.html", '<div id="content_views">第二篇正文</div>'.encode(), "text/html")),
                ("article_html", ("11.html", '<div id="content_views">第一篇正文</div>'.encode(), "text/html")),
            ],
        )
        assert retried.status_code == 303
        result = await wait_for_topic_result(client, retried.headers["location"])
        assert result.text.count("已从本地 HTML 导入") == 2
        result_page = BeautifulSoup(result.text, "lxml")
        output_link = result_page.select_one(".output-links a")
        assert output_link is not None
        title_links = result_page.select("a.article-result-title[href]")
        assert [link["href"] for link in title_links] == [
            f'{output_link["href"]}#article-1',
            f'{output_link["href"]}#article-2',
        ]
        output = await client.get(title_links[0]["href"])
        topic_home = await client.get("/topic")
        saved_link = BeautifulSoup(topic_home.text, "lxml").select_one("#topic-history a.result-title")
        assert saved_link is not None
        detail = BeautifulSoup((await client.get(saved_link["href"])).text, "lxml")
        assert detail.select_one(".output-links a")["href"] == output_link["href"]

    assert output.status_code == 200
    output_page = BeautifulSoup(output.text, "lxml")
    for link, expected_text in zip(title_links, ["第一篇正文", "第二篇正文"], strict=True):
        anchor = link["href"].split("#", 1)[1]
        section = output_page.find("section", id=anchor)
        assert section is not None
        assert expected_text in section.get_text()
    assert output.text.index("第一篇正文") < output.text.index("第二篇正文")
    assert requests == [topic_url, article_one, article_two, topic_url]


@pytest.mark.asyncio
@pytest.mark.parametrize("all_failed", [False, True])
async def test_topic_retry_fetches_only_the_selected_article(monkeypatch, tmp_path: Path, all_failed: bool) -> None:
    url = "https://blog.csdn.net/demo/category_123.html"
    first = "https://blog.csdn.net/demo/article/details/11"
    second = "https://blog.csdn.net/demo/article/details/22"
    settings = Settings.from_project_root(tmp_path)
    service = TopicService(ArchiveService(settings))
    fetched = []
    unavailable = {first, second} if all_failed else {second}

    def fetch(source, *, referer=None):
        fetched.append(source)
        if source in unavailable:
            raise FetchError("暂时无法下载")
        if source == url:
            html = (
                '<div id="column"><ul class="column_article_list">'
                f'<li><a href="{first}">第一篇</a></li><li><a href="{second}">第二篇</a></li></ul></div>'
            )
        else:
            title = "第一篇" if source == first else "第二篇"
            html = f'<title>{title}</title><div id="content_views">{f"{title}正文。" * 10}</div>'
        return PageSnapshot(source, source, html)

    monkeypatch.setattr(main, "settings", settings)
    monkeypatch.setattr(main, "topic_service", service)
    monkeypatch.setattr(main, "topic_jobs", TopicJobs())
    monkeypatch.setattr(service.archive_service.fetcher, "fetch", fetch)
    monkeypatch.setattr(topic_module, "sleep", lambda _: None)

    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        invalid = await client.post("/topic", data={"topic_url": url, "article_limit": "-1"})
        assert invalid.status_code == 400
        assert fetched == []
        submission = await client.post("/topic", data={"topic_url": url, "article_limit": "0"})
        initial = await wait_for_topic_result(client, submission.headers["location"])
        if not all_failed:
            # An older HTML archive can be retried after the process loses its in-memory jobs.
            (next((settings.data_dir / "topics").glob("*/*/*/metadata.json")).parent / TopicService.BODY_CACHE).unlink()
            monkeypatch.setattr(main, "topic_jobs", TopicJobs())
            listing = BeautifulSoup((await client.get("/topic")).text, "lxml")
            initial = await client.get(listing.select_one("#topic-history a.result-title")["href"])
        page = BeautifulSoup(initial.text, "lxml")
        retry_form = page.select_one('form[action$="/retry/2"]')
        assert retry_form is not None
        assert page.select_one("[data-failed-filter]") is not None
        assert retry_form.find_parent("li")["data-article-status"] == "failed"
        previous_output = page.select_one(".output-links a")
        if previous_output:
            previous_bytes = (await client.get(previous_output["href"])).content

        retry = await client.post(retry_form["action"])
        assert retry.status_code == 303
        still_failed = await wait_for_topic_result(client, retry.headers["location"])
        assert "暂时无法下载" in still_failed.text
        if previous_output:
            assert (await client.get(previous_output["href"])).content == previous_bytes

        unavailable.remove(second)
        retry_page = BeautifulSoup(still_failed.text, "lxml")
        retry = await client.post(retry_page.select_one('form[action$="/retry/2"]')["action"])
        updated = await wait_for_topic_result(client, retry.headers["location"])
        result = BeautifulSoup(updated.text, "lxml")
        assert result.select_one('form[action$="/retry/2"]') is None
        output = await client.get(result.select_one(".output-links a")["href"])
        saved = BeautifulSoup(output.text, "lxml")
        assert saved.select_one("#article-2").h2.get_text() == "第二篇"
        assert (saved.select_one("#article-1") is None) == all_failed
        if not all_failed:
            assert "第一篇正文" in saved.select_one("#article-1").get_text()

    assert fetched == [url, first, second, second, second]


@pytest.mark.asyncio
@pytest.mark.parametrize("has_archive", [True, False])
async def test_topic_batch_retry_uses_selected_or_current_failed_articles(monkeypatch, tmp_path: Path, has_archive: bool) -> None:
    topic = "https://blog.csdn.net/demo/category_123.html"
    first, second, third = (f"https://blog.csdn.net/demo/article/details/{i}" for i in (11, 22, 33))
    settings = Settings.from_project_root(tmp_path)
    service = TopicService(ArchiveService(settings))
    fetched = []
    pages = {first: "第一篇原正文"} if has_archive else {}

    def fetch(url, *, referer=None):
        fetched.append(url)
        if url == topic:
            links = "".join(f'<li><a href="{article}">文章</a></li>' for article in (first, second, third))
            html = f'<div id="column"><ul class="column_article_list">{links}</ul></div>'
        elif url in pages:
            html = f'<title>{pages[url]}</title><div id="content_views"><p>{(pages[url] + "。") * 10}</p></div>'
        else:
            raise FetchError("暂时无法下载")
        return PageSnapshot(url, url, html)

    monkeypatch.setattr(main, "settings", settings)
    monkeypatch.setattr(main, "topic_service", service)
    monkeypatch.setattr(main, "topic_jobs", TopicJobs())
    monkeypatch.setattr(service.archive_service.fetcher, "fetch", fetch)
    monkeypatch.setattr(topic_module, "sleep", lambda _: None)

    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        submission = await client.post("/topic", data={"topic_url": topic, "article_limit": 0})
        result = await wait_for_topic_result(client, submission.headers["location"])
        if has_archive:
            assert BeautifulSoup(result.text, "lxml").select_one(".output-links a") is not None
            history = BeautifulSoup((await client.get("/topic")).text, "lxml")
            result = await client.get(history.select_one("#topic-history a.result-title")["href"])
        page = BeautifulSoup(result.text, "lxml")
        batch_form = page.select_one('form[action$="/retry"]')
        assert batch_form is not None
        assert [item["value"] for item in page.select(f'input[form="{batch_form["id"]}"][name="positions"]')] == ["1", "2", "3"]
        action = batch_form["action"]
        fetched.clear()
        assert (await client.post(action, data={"mode": "selected"})).status_code == 400
        assert (await client.post(action, data={"mode": "selected", "positions": "4"})).status_code == 400
        assert not fetched

        if has_archive:
            output_url = page.select_one(".output-links a")["href"]
            original_output = (await client.get(output_url)).content
            del pages[first]
            retry = await client.post(action, data={"mode": "selected", "positions": "1"})
            assert retry.status_code == 303
            failed = await wait_for_topic_result(client, retry.headers["location"])
            assert "已保留原正文" in failed.text
            assert (await client.get(output_url)).content == original_output
            assert fetched == [first]
            fetched.clear()

        pages[second] = "第二篇新正文"
        retry = await client.post(action, data={"mode": "selected", "positions": ["2", "1", "2"]})
        assert retry.status_code == 303
        updated = await wait_for_topic_result(client, retry.headers["location"])
        assert fetched == [first, second]
        page = BeautifulSoup(updated.text, "lxml")
        output_url = page.select_one(".output-links a")["href"]
        output = BeautifulSoup((await client.get(output_url)).text, "lxml")
        assert "第二篇新正文" in output.select_one("#article-2").get_text()
        if has_archive:
            assert "第一篇原正文" in output.select_one("#article-1").get_text()
            assert "暂时无法下载" in page.select_one('[data-article-status="success"]').get_text()

        fetched.clear()
        pages.update({first: "第一篇更新正文", third: "第三篇新正文"})
        retry = await client.post(page.select_one('form[action$="/retry"]')["action"], data={
            "mode": "failed", "positions": "2",
        })
        assert retry.status_code == 303
        updated = await wait_for_topic_result(client, retry.headers["location"])
        assert fetched == ([third] if has_archive else [first, third])
        page = BeautifulSoup(updated.text, "lxml")
        assert page.select_one('button[value="failed"]').has_attr("disabled")
        output = BeautifulSoup((await client.get(output_url)).text, "lxml")
        assert [article["id"] for article in output.select(".topic-article[id]")] == ["article-1", "article-2", "article-3"]
        assert "第三篇新正文" in output.select_one("#article-3").get_text()

        if has_archive:
            fetched.clear()
            retry = await client.post(action, data={"mode": "selected", "positions": "1"})
            assert retry.status_code == 303
            await wait_for_topic_result(client, retry.headers["location"])
            assert fetched == [first]
            assert "第一篇更新正文" in (await client.get(output_url)).text


@pytest.mark.asyncio
async def test_markdown_downloads_and_imports_one_failed_article(monkeypatch, tmp_path: Path) -> None:
    topic = "https://blog.csdn.net/demo/category_123.html"
    first = "https://blog.csdn.net/demo/article/details/11"
    second = "https://blog.csdn.net/demo/article/details/22"
    settings = Settings.from_project_root(tmp_path)
    service = ArchiveService(settings)
    fetched = []
    article_html = (
        '<title>示例文章</title><div id="content_views"><h2>示例</h2>'
        '<p>这一段保留在单篇和专题的 Markdown 中，用于验证正文不会在补档时丢失。</p>'
        '<pre class="language-go"><code>if a &lt; b {\n\t// ```\n}</code></pre>'
        '<ul><li>第一项</li></ul><img src="https://img.csdn.net/example.png" alt="示意图">'
        '<table><tr><th>名称</th><th>值</th></tr><tr><td>样例</td><td>42</td></tr></table></div>'
    )

    def fetch(source, *, referer=None):
        fetched.append(source)
        if source == second:
            raise FetchError("HTTPS 连接提前断开")
        html = (
            '<div id="column"><ul class="column_article_list">'
            f'<li><a href="{first}">第一篇</a></li><li><a href="{second}">第二篇</a></li></ul></div>'
            if source == topic else article_html
        )
        return PageSnapshot(source, source, html)

    monkeypatch.setattr(main, "settings", settings)
    monkeypatch.setattr(main, "archive_service", service)
    monkeypatch.setattr(main, "topic_service", TopicService(service))
    monkeypatch.setattr(main, "topic_jobs", TopicJobs())
    monkeypatch.setattr(service.fetcher, "fetch", fetch)
    monkeypatch.setattr(topic_module, "sleep", lambda _: None)
    with respx.mock as assets:
        image = assets.get("https://img.csdn.net/example.png").respond(200, content=b"image")
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            single = BeautifulSoup((await client.post("/archive", data={"url": first, "formats": "md"})).text, "lxml")
            single_link = single.select_one('a[href$="/article.md?bundle=1"]')
            assert single_link is not None
            assert single_link.get_text() == "下载 Markdown ZIP"
            single_url = single_link["href"]
            document = await client.get(single_url.split("?", 1)[0])
            original_markdown = document.content
            assert document.headers["content-disposition"] == 'attachment; filename="article.md"'
            assert f"原始 URL：[{first}]({first})" in document.text
            assert "````go\nif a < b {\n\t// ```\n}\n````" in document.text
            assert "| 名称 | 值 |" in document.text
            assert "第一项" in document.text
            assert "![示意图](assets/example-" in document.text
            assert service.index.search("示例文章")[0]["address"].endswith("article.md")
            single_download = await client.get(single_url)
            assert single_download.headers["content-type"] == "application/zip"
            assert single_download.headers["content-disposition"] == 'attachment; filename="article.zip"'
            single_asset = document.text.split("![示意图](", 1)[1].split(")", 1)[0]
            with ZipFile(BytesIO(single_download.content)) as bundle:
                assert set(bundle.namelist()) == {"article.md", single_asset}
                assert bundle.read("article.md") == document.content
                assert bundle.read(single_asset) == b"image"
            library = BeautifulSoup((await client.get("/")).text, "lxml")
            assert library.select_one("#library a.result-title")["href"] == single_url

            submit = await client.post("/topic", data={"topic_url": topic, "output_format": "md"})
            initial = BeautifulSoup((await wait_for_topic_result(client, submit.headers["location"])).text, "lxml")
            topic_bundle_url = initial.select_one(".output-links a")["href"]
            assert topic_bundle_url.endswith("/topic.md?bundle=1")
            link = topic_bundle_url.split("?", 1)[0]
            partial = await client.get(link)
            assert partial.headers["content-disposition"] == 'attachment; filename="topic.md"'
            assert "![示意图](assets/article-1-example-" in partial.text
            assert f"原始 URL：[{second}]({second})" in partial.text
            assert "HTTPS 连接提前断开" in partial.text

            history = BeautifulSoup((await client.get("/topic")).text, "lxml")
            detail_url = history.select_one("#topic-history a.result-title")["href"]
            detail = BeautifulSoup((await client.get(detail_url)).text, "lxml")
            assert detail.select_one(".output-links a")["href"] == topic_bundle_url
            form = detail.select_one('form[action$="/retry/2"][enctype="multipart/form-data"]')
            imported = '<title>补档文章</title><div id="content_views"><p>从本地恢复的正文</p></div>'
            invalid = await client.post(form["action"], files={"article_html": ("11.html", imported)})
            assert invalid.status_code == 400
            assert (await client.get(link)).content == partial.content
            retry = await client.post(form["action"], files={"article_html": ("22.html", imported)})
            updated = await wait_for_topic_result(client, retry.headers["location"])
            assert "已从本地 HTML 导入" in updated.text
            document = await client.get(link)
            assert "HTTPS 连接提前断开" not in document.text
            assert "从本地恢复的正文" in document.text
            for source in (topic, first, second):
                label = source.replace("_", r"\_")
                assert document.text.count(f"原始 URL：[{label}]({source})") == 1
            assert document.text.index("## 示例文章") < document.text.index("## 补档文章")
            assert "![示意图](assets/article-1-example-" in document.text
            asset = document.text.split("![示意图](", 1)[1].split(")", 1)[0]
            assert (await client.get(link.rsplit("/", 1)[0] + "/" + asset)).content == b"image"
            topic_download = await client.get(topic_bundle_url)
            assert topic_download.headers["content-disposition"] == 'attachment; filename="topic.zip"'
            with ZipFile(BytesIO(topic_download.content)) as bundle:
                assert set(bundle.namelist()) == {"topic.md", asset}
                assert bundle.read("topic.md") == document.content
                assert bundle.read(asset) == b"image"

            mixed = await client.post("/archive", data={"url": first, "formats": ["html", "md"]})
            assert mixed.status_code == 400
            image.respond(200, content=b"updated image")
            html = await client.post("/archive", data={"url": first, "formats": "html"})
            assert html.status_code == 200
            assert "Markdown ZIP" not in html.text
            library = BeautifulSoup((await client.get("/", params={"q": "示例文章"})).text, "lxml")
            saved = library.select_one("#library li")
            assert saved.select_one("a.result-title")["href"].endswith("/article.html")
            assert saved.select_one('.history-meta a[href$="/article.html"]').get_text() == "HTML"
            assert saved.select_one('a[href$="/article.md?bundle=1"]').get_text() == "下载 Markdown ZIP"
            html_output = await client.get(saved.select_one("a.result-title")["href"])
            new_asset = BeautifulSoup(html_output.text, "lxml").select_one("img")["src"]
            assert new_asset != single_asset
            assert (await client.get(html_output.url.join(new_asset))).content == b"updated image"
            retained = await client.get(single_url)
            with ZipFile(BytesIO(retained.content)) as bundle:
                assert bundle.read("article.md") == original_markdown
                assert bundle.read(single_asset) == b"image"
    assert fetched == [first, topic, first, second, first]


async def wait_for_topic_result(client: httpx.AsyncClient, job_url: str) -> httpx.Response:
    async with asyncio.timeout(3):
        while True:
            response = await client.get(job_url)
            if 'http-equiv="refresh"' not in response.text:
                return response
            await asyncio.sleep(0.01)
