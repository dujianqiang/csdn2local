from __future__ import annotations

import asyncio
import json
import os
import shutil
from pathlib import Path
from threading import Event

import httpx
import pytest
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

    def download(self, url: str, output_format: str, concurrency: int, *, on_progress, saved_articles=None):
        self.calls.append((url, output_format, concurrency))
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
        assert [field["value"] for field in form.select('input[name="formats"][checked]')] == ["pdf"]


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
    assert 'name="output_format"' in response.text
    assert response.text.count('name="output_format"') == 3
    assert "暂无专题下载记录" in response.text


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
            json.dumps({"title": title, "format": fmt}), encoding="utf-8"
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
        assert [link.get_text(strip=True) for link in links] == ["最新试下载", "旧版专题"]
        assert "试下载" in links[0].parent.get_text()
        assert "EPUB" in links[1].parent.get_text()
        for link in links:
            local = await client.get(link["href"])
            assert local.status_code == 200
            assert local.content.decode("utf-8") == f"本地归档：{link.get_text(strip=True)}"


@pytest.mark.asyncio
async def test_topic_form_submits_single_format_and_concurrency(monkeypatch, tmp_path: Path) -> None:
    output = tmp_path / "topic.epub"
    output.write_bytes(b"epub")
    result = TopicResult(
        status="partial",
        topic_title="测试专题",
        topic_url="https://blog.csdn.net/demo/topic",
        output_format="epub",
        output_path=output,
        metadata_path=tmp_path / "metadata.json",
        articles=[TopicArticle(position=1, url="https://blog.csdn.net/a", title="文章一")],
    )
    fake = FakeTopicService(result)
    monkeypatch.setattr(main, "topic_service", fake)
    monkeypatch.setattr(main, "topic_jobs", TopicJobs())
    monkeypatch.setattr(main, "_file_url", lambda path: "/files/topic.epub")
    form = {"topic_url": result.topic_url, "output_format": "epub", "concurrency": "3"}

    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        try:
            submission = await client.post("/topic", data=form)
            assert submission.status_code == 303
            job_url = submission.headers["location"]
            assert await asyncio.to_thread(fake.started.wait, 3)
            progress = await client.get(job_url)
            assert progress.status_code == 200
            assert progress.headers["Cache-Control"] == "no-store"
            assert "正在下载文章" in progress.text
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
        assert edited.select_one('input[name="output_format"][checked]')["value"] == "epub"
        assert edited.select_one('input[name="concurrency"]')["value"] == "3"

    assert response.status_code == 200
    assert "测试专题" in response.text
    assert "/files/topic.epub" in response.text
    assert not BeautifulSoup(response.text, "lxml").select("a.article-result-title")
    assert "重新下载专题" in response.text
    assert 'name="output_format" value="epub"' in response.text
    assert 'name="concurrency" value="3"' in response.text
    assert "专题共 3 篇，本次只处理前 2 篇" in response.text
    assert 'http-equiv="refresh"' not in response.text
    assert fake.calls == [(result.topic_url, "epub", 3)]


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
        assert saved_link["href"] == output_link["href"]

    assert output.status_code == 200
    output_page = BeautifulSoup(output.text, "lxml")
    for link, expected_text in zip(title_links, ["第一篇正文", "第二篇正文"], strict=True):
        anchor = link["href"].split("#", 1)[1]
        section = output_page.find("section", id=anchor)
        assert section is not None
        assert expected_text in section.get_text()
    assert output.text.index("第一篇正文") < output.text.index("第二篇正文")
    assert requests == [topic_url, article_one, article_two, topic_url]


async def wait_for_topic_result(client: httpx.AsyncClient, job_url: str) -> httpx.Response:
    async with asyncio.timeout(3):
        while True:
            response = await client.get(job_url)
            if 'http-equiv="refresh"' not in response.text:
                return response
            await asyncio.sleep(0.01)
