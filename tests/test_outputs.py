from __future__ import annotations

from app.outputs import write_html, write_pdf


def test_pdf_is_generated_from_offline_html(tmp_path) -> None:
    html_path = tmp_path / "article.html"
    pdf_path = tmp_path / "article.pdf"

    write_html(html_path, "测试文章", "<p>离线正文</p>")
    write_pdf(html_path, pdf_path)

    assert html_path.exists()
    assert pdf_path.read_bytes().startswith(b"%PDF")
