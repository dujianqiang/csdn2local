from __future__ import annotations

import shutil
from pathlib import Path

import httpx
import pytest

import app.main as main
from app.archive import ArchiveResult
from app.models import ArticleMetadata
from app.storage import ArchivePaths
from app.topic import TopicArticle, TopicResult


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

    def download(self, url: str, output_format: str, concurrency: str):
        self.calls.append((url, output_format, concurrency))
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
    assert "已下载文件" in response.text
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
    assert "暂无已下载文件。" in response.text


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
    assert "文章保存成功" in response.text
    assert fake.calls == [("https://blog.csdn.net/a", ["html"])]
    shutil.rmtree(tmp_path, ignore_errors=True)


@pytest.mark.asyncio
async def test_topic_page_has_navigation_single_format_and_default_concurrency() -> None:
    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/topic")

    assert response.status_code == 200
    assert "单个地址下载" in response.text
    assert "专题下载" in response.text
    assert 'name="concurrency"' in response.text
    assert 'value="1"' in response.text
    assert 'name="output_format"' in response.text
    assert response.text.count('name="output_format"') == 3


@pytest.mark.asyncio
async def test_topic_form_submits_single_format_and_concurrency(monkeypatch, tmp_path: Path) -> None:
    output = tmp_path / "topic.epub"
    output.write_bytes(b"epub")
    result = TopicResult(
        status="success",
        topic_title="测试专题",
        topic_url="https://blog.csdn.net/demo/topic",
        output_format="epub",
        output_path=output,
        metadata_path=tmp_path / "metadata.json",
        articles=[TopicArticle(position=1, url="https://blog.csdn.net/a", title="文章一")],
    )
    fake = FakeTopicService(result)
    monkeypatch.setattr(main, "topic_service", fake)
    monkeypatch.setattr(main, "_file_url", lambda path: "/files/topic.epub")

    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/topic",
            data={"topic_url": "https://blog.csdn.net/demo/topic", "output_format": "epub", "concurrency": "3"},
        )

    assert response.status_code == 200
    assert "测试专题" in response.text
    assert "/files/topic.epub" in response.text
    assert fake.calls == [("https://blog.csdn.net/demo/topic", "epub", "3")]
