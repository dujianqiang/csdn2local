from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright

from app.parser import render_article_document


class OutputError(RuntimeError):
    """An archive output could not be generated."""


def write_html(path: Path, title: str, body_html: str) -> None:
    path.write_text(render_article_document(title, body_html), encoding="utf-8")


def write_pdf(html_path: Path, pdf_path: Path) -> None:
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.goto(html_path.as_uri(), wait_until="load")
                page.pdf(
                    path=str(pdf_path),
                    format="A4",
                    print_background=True,
                    margin={"top": "18mm", "right": "14mm", "bottom": "18mm", "left": "14mm"},
                )
            finally:
                browser.close()
    except Exception as exc:
        raise OutputError(f"PDF 生成失败：{exc}") from exc
