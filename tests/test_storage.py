from __future__ import annotations

from app.index import ArticleIndex
from app.models import ArticleMetadata
from app.storage import ArchivePaths, article_key, normalize_url, sanitize_filename


def test_filename_and_article_key_are_windows_safe() -> None:
    assert sanitize_filename('a<b>c:"d/e\\f|g?*') == "a_b_c__d_e_f_g__"
    assert sanitize_filename("CON") == "_CON"
    assert article_key(None, "标题:示例", "https://blog.csdn.net/a/article/details/1") == article_key(
        None, "标题:示例", "https://blog.csdn.net/a/article/details/1"
    )


def test_normalize_url_removes_fragment() -> None:
    assert normalize_url("HTTPS://BLOG.CSDN.NET/a#part") == "https://blog.csdn.net/a"


def test_index_upserts_and_searches_metadata(tmp_path) -> None:
    index = ArticleIndex(tmp_path / "index.sqlite3")
    metadata = ArticleMetadata(
        title="First title",
        original_url="https://blog.csdn.net/a/1#top",
        domain="blog.csdn.net",
        author="Alice",
        tags=["python"],
        formats=["html"],
    )
    archive = tmp_path / "blog.csdn.net" / "article"
    archive.mkdir(parents=True)
    (archive / "article.html").write_text("<html></html>", encoding="utf-8")
    index.upsert(metadata, ArchivePaths(archive))

    results = index.search("python")

    assert len(results) == 1
    assert results[0]["title"] == "First title"
    assert results[0]["address"].endswith("article.html")
