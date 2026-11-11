from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from app.models import ArticleMetadata
from app.storage import ArchivePaths, normalize_url


class ArticleIndex:
    def __init__(self, database_path: Path):
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS articles (
                    original_url TEXT PRIMARY KEY,
                    archive_dir TEXT NOT NULL,
                    title TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    author TEXT,
                    published_at TEXT,
                    tags_json TEXT NOT NULL,
                    formats_json TEXT NOT NULL,
                    saved_at TEXT NOT NULL,
                    warnings_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_articles_title ON articles(title);
                CREATE INDEX IF NOT EXISTS idx_articles_domain ON articles(domain);
                CREATE INDEX IF NOT EXISTS idx_articles_author ON articles(author);
                """
            )

    def upsert(self, metadata: ArticleMetadata, paths: ArchivePaths) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO articles (
                    original_url, archive_dir, title, domain, author, published_at,
                    tags_json, formats_json, saved_at, warnings_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(original_url) DO UPDATE SET
                    archive_dir=excluded.archive_dir,
                    title=excluded.title,
                    domain=excluded.domain,
                    author=excluded.author,
                    published_at=excluded.published_at,
                    tags_json=excluded.tags_json,
                    formats_json=excluded.formats_json,
                    saved_at=excluded.saved_at,
                    warnings_json=excluded.warnings_json
                """,
                (
                    normalize_url(metadata.original_url),
                    str(paths.archive_dir),
                    metadata.title,
                    metadata.domain,
                    metadata.author,
                    metadata.published_at,
                    json.dumps(metadata.tags, ensure_ascii=False),
                    json.dumps(metadata.formats),
                    metadata.saved_at,
                    json.dumps(metadata.warnings, ensure_ascii=False),
                ),
            )

    def search(self, keyword: str) -> list[dict[str, Any]]:
        term = f"%{keyword.strip()}%"
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT original_url, archive_dir, title, domain, author, published_at,
                       tags_json, formats_json, saved_at, warnings_json
                FROM articles
                WHERE title LIKE ? COLLATE NOCASE
                   OR domain LIKE ? COLLATE NOCASE
                   OR original_url LIKE ? COLLATE NOCASE
                   OR COALESCE(author, '') LIKE ? COLLATE NOCASE
                   OR tags_json LIKE ? COLLATE NOCASE
                ORDER BY saved_at DESC
                """,
                (term, term, term, term, term),
            ).fetchall()
        return [self._row_to_result(row) for row in rows]

    def archive_dir_for_url(self, original_url: str) -> Path | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT archive_dir FROM articles WHERE original_url = ?",
                (normalize_url(original_url),),
            ).fetchone()
        return Path(row["archive_dir"]) if row else None

    @staticmethod
    def _row_to_result(row: sqlite3.Row) -> dict[str, Any]:
        archive_dir = Path(row["archive_dir"])
        html = archive_dir / "article.html"
        pdf = archive_dir / "article.pdf"
        target = html if html.exists() else pdf if pdf.exists() else None
        return {
            "title": row["title"],
            "address": str(target) if target else None,
            "original_url": row["original_url"],
        }
