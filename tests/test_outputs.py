from __future__ import annotations

import subprocess
import sys
from contextlib import nullcontext
from unittest.mock import Mock

import pytest
from bs4 import BeautifulSoup
from playwright.sync_api import Error as PlaywrightError, sync_playwright
from pypdf import PdfReader

from app import outputs
from app.outputs import OutputError, write_html, write_pdf
from app.parser import render_article_document
from app.topic_outputs import render_topic_document


def test_generated_html_preserves_dark_code_style_and_box_characters() -> None:
    body = "<pre><code>┌────┐\n│任务│\n└────┘</code></pre>"

    html = render_article_document("测试文章", body)

    assert "background: #282c34" in html
    assert "white-space: pre" in html
    assert "overflow-x: auto" in html
    assert "┌────┐" in html
    assert "└────┘" in html


def test_generated_html_wraps_code_blocks_in_closed_details() -> None:
    html = render_article_document("测试文章", "<pre><code>line 1\nline 2</code></pre>")
    soup = BeautifulSoup(html, "lxml")
    details = soup.select("details.code-block")

    assert len(details) == 1
    assert not details[0].has_attr("open")
    assert details[0].summary.get_text(strip=True) == "代码块 1"
    assert "line 1\nline 2" in details[0].get_text()
    assert "@media print" in html


@pytest.fixture
def article_with_long_code() -> str:
    return "<p>BODY_PRESENT</p><pre><code>CODE_PRESENT\n    " + "x" * 180 + " LINE_END_PRESENT</code></pre>"


def assert_pdf_contains_code(pdf_path) -> None:
    text = "\n".join(page.extract_text() for page in PdfReader(pdf_path).pages)

    assert "BODY_PRESENT" in text
    assert "CODE_PRESENT" in text
    assert "x" * 180 + "LINE_END_PRESENT" in "".join(text.split())


@pytest.mark.parametrize("kind", ["article", "topic"])
def test_printing_generated_html_keeps_folded_code_and_long_lines(tmp_path, kind, article_with_long_code) -> None:
    html_path = tmp_path / "archive.html"
    pdf_path = tmp_path / "archive.pdf"
    if kind == "article":
        write_html(html_path, "Article", article_with_long_code)
    else:
        html = render_topic_document("Topic", [{"position": 1, "title": "Article", "body_html": article_with_long_code}])
        html_path.write_text(html, encoding="utf-8")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(html_path.as_uri())
            assert page.locator("details.code-block").get_attribute("open") is None
            page.pdf(path=str(pdf_path), format="A4")
        finally:
            browser.close()

    assert_pdf_contains_code(pdf_path)


def test_pdf_export_keeps_code_in_existing_archived_html(tmp_path, article_with_long_code) -> None:
    html_path = tmp_path / "article.html"
    pdf_path = tmp_path / "article.pdf"
    html = (
        "<!doctype html><style>pre, pre code { white-space: pre; } pre { overflow-x: auto; }</style>"
        + article_with_long_code.replace("<pre>", '<details class="code-block"><summary>Code</summary><pre>')
        + "</details>"
    )
    html_path.write_text(html, encoding="utf-8")

    write_pdf(html_path, pdf_path)

    assert_pdf_contains_code(pdf_path)
    assert html_path.read_text(encoding="utf-8") == html


@pytest.mark.parametrize("missing", [True, False])
def test_pdf_installs_chromium_only_when_missing(monkeypatch, tmp_path, missing) -> None:
    chromium = Mock()
    browser = Mock()
    chromium.launch.side_effect = (
        [PlaywrightError("BrowserType.launch: Executable doesn't exist at browser-cache"), browser, browser]
        if missing else [browser, browser]
    )
    monkeypatch.setattr(outputs, "sync_playwright", lambda: nullcontext(Mock(chromium=chromium)))
    install = Mock()
    monkeypatch.setattr(subprocess, "run", install)
    html_path = tmp_path / "article.html"
    pdf_path = tmp_path / "article.pdf"

    write_pdf(html_path, pdf_path)
    write_pdf(html_path, pdf_path)

    assert install.call_count == int(missing)
    if missing:
        assert install.call_args.args[0] == [
            sys.executable, "-m", "playwright", "install", "--only-shell", "chromium"
        ]
    assert browser.new_page.return_value.pdf.call_count == 2


def test_pdf_explains_download_failure_and_allows_retry(monkeypatch, tmp_path) -> None:
    chromium = Mock()
    browser = Mock()
    missing = PlaywrightError("BrowserType.launch: Executable doesn't exist at browser-cache")
    chromium.launch.side_effect = [missing, missing, browser]
    monkeypatch.setattr(outputs, "sync_playwright", lambda: nullcontext(Mock(chromium=chromium)))
    install = Mock(side_effect=[subprocess.CalledProcessError(1, "playwright"), None])
    monkeypatch.setattr(subprocess, "run", install)
    html_path = tmp_path / "article.html"
    pdf_path = tmp_path / "article.pdf"

    with pytest.raises(OutputError, match="Chromium 下载失败.*重试"):
        write_pdf(html_path, pdf_path)
    write_pdf(html_path, pdf_path)

    assert install.call_count == 2
    browser.new_page.return_value.pdf.assert_called_once()


def test_pdf_reports_linux_system_dependencies_without_redownloading(monkeypatch, tmp_path) -> None:
    chromium = Mock()
    chromium.launch.side_effect = PlaywrightError("Host system is missing dependencies to run browsers.")
    monkeypatch.setattr(outputs, "sync_playwright", lambda: nullcontext(Mock(chromium=chromium)))
    monkeypatch.setattr(sys, "platform", "linux")
    install = Mock()
    monkeypatch.setattr(subprocess, "run", install)

    with pytest.raises(OutputError, match="Linux.*playwright install-deps chromium"):
        write_pdf(tmp_path / "article.html", tmp_path / "article.pdf")

    install.assert_not_called()
