from __future__ import annotations

from app.outputs import write_html, write_pdf
from app.parser import render_article_document


def test_generated_html_preserves_dark_code_style_and_box_characters() -> None:
    body = "<pre><code>┌────┐\n│任务│\n└────┘</code></pre>"

    html = render_article_document("测试文章", body)

    assert "background: #282c34" in html
    assert "white-space: pre" in html
    assert "overflow-x: auto" in html
    assert "┌────┐" in html
    assert "└────┘" in html


def test_pdf_is_generated_from_offline_html(tmp_path) -> None:
    html_path = tmp_path / "article.html"
    pdf_path = tmp_path / "article.pdf"

    write_html(html_path, "测试文章", "<p>离线正文</p>")
    write_pdf(html_path, pdf_path)

    assert html_path.exists()
    assert pdf_path.read_bytes().startswith(b"%PDF")
