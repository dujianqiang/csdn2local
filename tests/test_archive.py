from __future__ import annotations

from pathlib import Path

import pytest

import app.archive as archive_module
from app.archive import ArchiveService
from app.config import Settings
from app.fetcher import PageSnapshot
from app.models import ArticleMetadata
from app.parser import ParsedArticle
from app.resources import ResourceDownloadResult


class FakeFetcher:
    def fetch(self, url: str) -> PageSnapshot:
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
