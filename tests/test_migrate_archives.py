from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import quote

import httpx
import pytest
from bs4 import BeautifulSoup

from app import main
from app.archive import ArchiveService
from app.config import Settings
from app.index import ArticleIndex
from app.migrate_archives import migrate_archives, plan_migration
from app.models import ArticleMetadata
from app.storage import ArchivePaths


@pytest.mark.asyncio
async def test_migration_keeps_old_links_index_resources_and_duplicate_versions(monkeypatch, tmp_path: Path) -> None:
    settings = Settings.from_project_root(tmp_path)
    root = settings.data_dir
    domain = root / "blog.csdn.net"
    article = ArchivePaths(domain / "11_示例文章")
    article.assets.mkdir(parents=True)
    article.html.write_text('<img src="assets/image.png">', encoding="utf-8")
    (article.assets / "image.png").write_bytes(b"article image")
    metadata = ArticleMetadata(
        title="示例文章", original_url="https://blog.csdn.net/demo/article/details/11",
        domain="blog.csdn.net", article_id="11", formats=["html"],
    )
    article.metadata.write_text(json.dumps(metadata.to_dict()), encoding="utf-8")
    old_index = root / "index.sqlite3"
    ArticleIndex(old_index).upsert(metadata, article)

    topic_url = "https://blog.csdn.net/demo/category_123.html"
    older = domain / "topics" / "preview-5-topic-old"
    newer = domain / "topics" / "preview-5-html-topic-new"
    for folder, title, mtime in [(older, "旧标题", 1700000000), (newer, "专题示例", 1700000100)]:
        folder.mkdir(parents=True)
        output = folder / "topic.html"
        output.write_text(f'<section id="article-1">{title}</section>', encoding="utf-8")
        os.utime(output, (mtime, mtime))
        (folder / "metadata.json").write_text(json.dumps({
            "title": title, "original_url": topic_url, "format": "html", "article_limit": 5,
            "articles": [{"position": 1, "title": "示例文章", "url": metadata.original_url}],
        }), encoding="utf-8")

    moves = plan_migration(root)
    assert len(moves) == 3
    assert article.html.is_file() and newer.is_dir()
    assert not settings.index_path.exists()
    migrate_archives(settings, moves)
    assert plan_migration(root) == []
    migrate_archives(settings, [])

    topic_dir = root / "topics" / "123_专题示例" / "前5篇"
    assert "专题示例" in (topic_dir / "html" / "topic.html").read_text(encoding="utf-8")
    assert "旧标题" in (topic_dir / "html-旧版-2" / "topic.html").read_text(encoding="utf-8")
    assert not domain.exists()
    assert (root / ".internal" / "legacy" / newer.relative_to(root) / "topic.html").is_file()
    assert (root / ".internal" / "legacy" / "index.sqlite3").is_file()

    monkeypatch.setattr(main, "settings", settings)
    monkeypatch.setattr(main, "archive_service", ArchiveService(settings))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://testserver") as client:
        home = BeautifulSoup((await client.get("/")).text, "lxml")
        current_article = home.select_one(".result-title")["href"]
        assert current_article.startswith("/files/articles/")
        old_article = "/files/" + quote(article.archive_dir.relative_to(root).as_posix(), safe="/")
        assert (await client.get(old_article + "/article.html")).status_code == 200
        assert (await client.get(old_article + "/assets/image.png")).content == b"article image"
        old_topic = "/files/" + newer.relative_to(root).as_posix() + "/topic.html"
        assert 'id="article-1"' in (await client.get(old_topic)).text
        detail = await client.get("/topic/history/blog.csdn.net/preview-5-html-topic-new")
        assert detail.status_code == 200
        page = BeautifulSoup(detail.text, "lxml")
        assert len(page.select(".version-list a")) == 2
        assert page.select_one(".output-links a")["href"].startswith("/files/topics/")
        assert (await client.get("/files/.internal/legacy/index.sqlite3")).status_code == 404
