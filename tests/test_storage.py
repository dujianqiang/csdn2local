from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest

from app.config import Settings
from app.index import ArticleIndex
from app.models import ArticleMetadata
from app.storage import ArchivePaths, ArchiveStore, article_key, normalize_url, sanitize_filename


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


def test_index_lists_newest_downloads_and_falls_back_to_pdf(tmp_path) -> None:
    index = ArticleIndex(tmp_path / "index.sqlite3")
    older = ArticleMetadata(
        title="Older",
        original_url="https://blog.csdn.net/a/older",
        domain="blog.csdn.net",
        saved_at="2026-01-01T00:00:00+00:00",
        formats=["pdf"],
    )
    newer = ArticleMetadata(
        title="Newer",
        original_url="https://blog.csdn.net/a/newer",
        domain="blog.csdn.net",
        saved_at="2026-01-02T00:00:00+00:00",
        formats=["html"],
    )
    older_archive = tmp_path / "blog.csdn.net" / "older"
    newer_archive = tmp_path / "blog.csdn.net" / "newer"
    older_archive.mkdir(parents=True)
    newer_archive.mkdir(parents=True)
    (older_archive / "article.pdf").write_bytes(b"pdf")
    (newer_archive / "article.html").write_text("<html></html>", encoding="utf-8")
    index.upsert(older, ArchivePaths(older_archive))
    index.upsert(newer, ArchivePaths(newer_archive))

    results = index.list_all()

    assert [item["title"] for item in results] == ["Newer", "Older"]
    assert results[0]["address"].endswith("article.html")
    assert results[1]["address"].endswith("article.pdf")


def test_index_lists_no_records_as_empty(tmp_path) -> None:
    index = ArticleIndex(tmp_path / "index.sqlite3")

    assert index.list_all() == []


@pytest.mark.parametrize("recover_on_second_attempt", [True, False])
def test_commit_handles_windows_publish_denial_without_losing_original(
    monkeypatch, tmp_path, recover_on_second_attempt: bool
) -> None:
    store = ArchiveStore(Settings.from_project_root(tmp_path))
    target = ArchivePaths(store.settings.data_dir / "blog.csdn.net" / "topics" / "old-epub")
    target.archive_dir.mkdir(parents=True)
    target.metadata.write_text("original", encoding="utf-8")
    staging = store.create_staging()
    staging.archive_dir.mkdir()
    staging.metadata.write_text("repaired", encoding="utf-8")
    replace_directory = Path.replace
    failures = []

    def replace_path(source: Path, destination: Path):
        publishing = source == staging.archive_dir or source.name.startswith(".incoming-")
        if destination == target.archive_dir and publishing:
            if not recover_on_second_attempt or not failures:
                error = PermissionError("Windows denied the directory move")
                error.winerror = 5
                failures.append(source)
                raise error
        return replace_directory(source, destination)

    monkeypatch.setattr(Path, "replace", replace_path)
    monkeypatch.setattr("app.storage.sleep", Mock())

    if recover_on_second_attempt:
        store.commit(staging, target)
        assert target.metadata.read_text(encoding="utf-8") == "repaired"
        assert failures == [staging.archive_dir]
    else:
        with pytest.raises(PermissionError, match="Windows denied"):
            store.commit(staging, target)
        assert target.metadata.read_text(encoding="utf-8") == "original"
        assert any(path.parent == target.archive_dir.parent for path in failures)
    assert list(target.archive_dir.parent.iterdir()) == [target.archive_dir]
