from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class ArticleMetadata:
    title: str
    original_url: str
    domain: str
    article_id: str | None = None
    author: str | None = None
    published_at: str | None = None
    tags: list[str] = field(default_factory=list)
    saved_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    formats: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ArticleMetadata":
        return cls(
            title=str(value.get("title", "")),
            original_url=str(value.get("original_url", "")),
            domain=str(value.get("domain", "")),
            article_id=value.get("article_id"),
            author=value.get("author"),
            published_at=value.get("published_at"),
            tags=list(value.get("tags", [])),
            saved_at=str(value.get("saved_at") or datetime.now(timezone.utc).isoformat()),
            formats=list(value.get("formats", [])),
            warnings=list(value.get("warnings", [])),
        )
