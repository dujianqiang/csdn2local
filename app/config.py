from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


DEFAULT_TOPIC_ARTICLE_LIMIT = 5
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/157.0.0.0 Safari/537.36"
)


@dataclass(frozen=True)
class Settings:
    project_root: Path
    data_dir: Path
    index_path: Path
    host: str = "127.0.0.1"
    port: int = 8000
    request_timeout_seconds: float = 30.0
    topic_article_limit: int = DEFAULT_TOPIC_ARTICLE_LIMIT
    user_agent: str = DEFAULT_USER_AGENT

    @classmethod
    def from_project_root(cls, project_root: Path | None = None) -> "Settings":
        root = (project_root or Path(__file__).resolve().parent.parent).resolve()
        data_dir = root / "data"
        os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(root / ".playwright-browsers"))
        limit = int(os.getenv("CSDN2LOCAL_TOPIC_ARTICLE_LIMIT", str(DEFAULT_TOPIC_ARTICLE_LIMIT)))
        if limit < 0:
            raise ValueError("CSDN2LOCAL_TOPIC_ARTICLE_LIMIT 必须为非负整数")
        return cls(
            project_root=root,
            data_dir=data_dir,
            index_path=data_dir / "index.sqlite3",
            topic_article_limit=limit,
            user_agent=os.getenv("CSDN2LOCAL_USER_AGENT", DEFAULT_USER_AGENT).strip() or DEFAULT_USER_AGENT,
        )

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)


settings = Settings.from_project_root()
