from __future__ import annotations

import shutil
from pathlib import Path

import httpx
import pytest

import app.main as main
from app.archive import ArchiveResult
from app.models import ArticleMetadata
from app.storage import ArchivePaths


class FakeIndex:
    def __init__(self, result):
        self.result = result

    def search(self, keyword: str):
        return self.result if keyword == "python" else []


class FakeService:
    def __init__(self, result):
        self.index = FakeIndex([])
        self.result = result
        self.calls = []

    def archive(self, url: str, formats: list[str]):
        self.calls.append((url, formats))
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
