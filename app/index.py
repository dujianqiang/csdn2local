from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.models import ArticleMetadata
from app.storage import ArchivePaths, normalize_url


class ArticleIndex:
    def __init__(self, database_path: Path, *, legacy_path: Path | None = None):
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        if legacy_path and legacy_path.is_file() and not database_path.exists():
            temporary = database_path.with_name(f".index-{uuid4().hex}.sqlite3")
            try:
                with closing(sqlite3.connect(f"{legacy_path.resolve().as_uri()}?mode=ro", uri=True)) as source:
                    with closing(sqlite3.connect(temporary)) as destination:
                        source.backup(destination)
                if not database_path.exists():
                    temporary.replace(database_path)
            finally:
                temporary.unlink(missing_ok=True)
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        with closing(self.connect()) as connection, connection:
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
        with closing(self.connect()) as connection, connection:
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
        with closing(self.connect()) as connection:
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
        return self._rows_to_results(rows)

    def list_all(self) -> list[dict[str, Any]]:
        with closing(self.connect()) as connection:
            rows = connection.execute(
                """
                SELECT original_url, archive_dir, title, domain, author, published_at,
                       tags_json, formats_json, saved_at, warnings_json
                FROM articles
                ORDER BY saved_at DESC
                """
            ).fetchall()
        return self._rows_to_results(rows)

    def archive_dir_for_url(self, original_url: str) -> Path | None:
        with closing(self.connect()) as connection:
            row = connection.execute(
                "SELECT archive_dir FROM articles WHERE original_url = ?",
                (normalize_url(original_url),),
            ).fetchone()
        return Path(row["archive_dir"]) if row else None

    def relocate(self, source: Path, destination: Path) -> None:
        with closing(self.connect()) as connection, connection:
            connection.execute(
                "UPDATE articles SET archive_dir = ? WHERE archive_dir = ?",
                (str(destination), str(source)),
            )

    @classmethod
    def _rows_to_results(cls, rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
        results = []
        for row in rows:
            result = cls._row_to_result(row)
            if result["address"]:
                results.append(result)
        return results

    @staticmethod
    def _row_to_result(row: sqlite3.Row) -> dict[str, Any]:
        paths = ArchivePaths(Path(row["archive_dir"]))
        outputs = {name: str(path) for name, path in paths.article_outputs().items()}
        return {
            "title": row["title"],
            "address": next(iter(outputs.values()), None),
            "outputs": outputs,
            "original_url": row["original_url"],
        }
