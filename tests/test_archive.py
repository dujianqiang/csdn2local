from __future__ import annotations

import json
from pathlib import Path

import pytest
from bs4 import BeautifulSoup
from pypdf import PdfReader

import app.archive as archive_module
from app.archive import ArchiveService
from app.config import Settings
from app.fetcher import PageSnapshot
from app.models import ArticleMetadata
from app.parser import ParsedArticle
from app.resources import ResourceDownloadResult
from app.storage import ArchivePaths


class FakeFetcher:
    def fetch(self, url: str, *, referer: str | None = None) -> PageSnapshot:
        return PageSnapshot(url, url, "<html></html>")


class FakeParser:
    def parse(self, html: str, source_url: str) -> ParsedArticle:
        metadata = ArticleMetadata(
            title="测试文章",
            original_url=source_url,
            domain="blog.csdn.net",
            article_id="123",
        )
        return ParsedArticle(metadata, "<p>正文</p>", [])


class FakeResources:
    def __init__(self, warnings: list[str]):
        self.warnings = warnings

    def download(self, body_html: str, source_url: str, assets_dir: Path) -> ResourceDownloadResult:
        assets_dir.mkdir(parents=True, exist_ok=True)
        return ResourceDownloadResult(body_html, self.warnings)


def make_service(tmp_path: Path, warnings: list[str] | None = None) -> ArchiveService:
    service = ArchiveService(Settings.from_project_root(tmp_path))
    service.fetcher = FakeFetcher()
    service.parser = FakeParser()
    service.resources = FakeResources(warnings or [])
    return service


def test_archive_keeps_html_when_pdf_generation_fails(monkeypatch, tmp_path: Path) -> None:
    service = make_service(tmp_path, ["资源下载失败：image.png"])

    def fail_pdf(html_path: Path, pdf_path: Path) -> None:
        raise archive_module.OutputError("PDF 生成失败：浏览器不可用")

    monkeypatch.setattr(archive_module, "write_pdf", fail_pdf)

    result = service.archive("https://blog.csdn.net/demo/article/details/123", ["html", "pdf"])

    assert result.status == "partial"
    assert result.metadata.formats == ["html"]
    assert result.paths.html.exists()
    assert not result.paths.pdf.exists()
    assert any("资源下载失败" in warning for warning in result.warnings)
    assert any("PDF 生成失败" in warning for warning in result.warnings)


def test_archive_defaults_to_html_and_overwrites_index(tmp_path: Path) -> None:
    service = make_service(tmp_path)

    result = service.archive("https://blog.csdn.net/demo/article/details/123")

    assert result.status == "success"
    assert result.metadata.formats == ["html"]
    assert result.paths.html.exists()
    assert not result.paths.pdf.exists()
    assert len(service.index.search("测试文章")) == 1


@pytest.mark.parametrize("output_format", ["html", "pdf", "md"])
def test_archive_labels_the_submitted_article_url(monkeypatch, tmp_path: Path, output_format: str) -> None:
    service = make_service(tmp_path)
    url = "https://blog.csdn.net/demo/article/details/123?a=1&b=2"
    final_url = "https://blog.csdn.net/demo/article/details/123"
    monkeypatch.setattr(service.fetcher, "fetch", lambda source, *, referer=None: PageSnapshot(source, final_url, ""))

    result = service.archive(url, [output_format])

    if output_format == "html":
        document = BeautifulSoup(result.paths.html.read_text(encoding="utf-8"), "lxml")
        note = document.select_one("h1 + p")
        assert note is not None and note.get_text() == f"原始 URL：{url}"
        assert note.a["href"] == url
    elif output_format == "pdf":
        page = PdfReader(result.paths.pdf).pages[0]
        assert url in "".join(page.extract_text().split())
        assert any(link.get_object().get("/A", {}).get("/URI") == url for link in page["/Annots"])
    else:
        lines = result.paths.md.read_text(encoding="utf-8").splitlines()
        assert lines[2].startswith("原始 URL：")
        assert f"]({url})" in lines[2]


def test_archive_retains_legacy_pdf_when_saving_another_format(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    url = "https://blog.csdn.net/demo/article/details/123"
    legacy = ArchivePaths(service.settings.data_dir / "blog.csdn.net" / "article")
    legacy.archive_dir.mkdir(parents=True)
    legacy.pdf.write_bytes(b"legacy PDF")
    metadata = ArticleMetadata("测试文章", url, "blog.csdn.net", formats=["pdf"])
    service.index.upsert(metadata, legacy)

    result = service.archive(url, ["html"])

    assert result.paths.pdf.read_bytes() == legacy.pdf.read_bytes() == b"legacy PDF"
    assert json.loads(result.paths.metadata.read_text(encoding="utf-8"))["formats"] == ["html", "pdf"]
    record, = service.index.list_all()
    assert record["outputs"] == {"html": str(result.paths.html), "pdf": str(result.paths.pdf)}
