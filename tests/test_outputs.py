from __future__ import annotations

from app.outputs import write_html, write_pdf
from app.parser import render_article_document
from bs4 import BeautifulSoup


def test_generated_html_preserves_dark_code_style_and_box_characters() -> None:
    body = "<pre><code>┌────┐\n│任务│\n└────┘</code></pre>"

    html = render_article_document("测试文章", body)

    assert "background: #282c34" in html
    assert "white-space: pre" in html
    assert "overflow-x: auto" in html
    assert "┌────┐" in html
    assert "└────┘" in html


def test_generated_html_wraps_code_blocks_in_open_details() -> None:
    html = render_article_document("测试文章", "<pre><code>line 1\nline 2</code></pre>")
    soup = BeautifulSoup(html, "lxml")
    details = soup.select("details.code-block")

    assert len(details) == 1
    assert details[0].has_attr("open")
    assert details[0].summary.get_text(strip=True) == "代码块 1"
    assert "line 1\nline 2" in details[0].get_text()
    assert "@media print" in html


def test_pdf_is_generated_from_offline_html(tmp_path) -> None:
    html_path = tmp_path / "article.html"
    pdf_path = tmp_path / "article.pdf"

    write_html(html_path, "测试文章", "<p>离线正文</p>")
    write_pdf(html_path, pdf_path)

    assert html_path.exists()
    assert pdf_path.read_bytes().startswith(b"%PDF")
