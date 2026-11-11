from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    project_root: Path
    data_dir: Path
    index_path: Path
    host: str = "127.0.0.1"
    port: int = 8000
    request_timeout_seconds: float = 30.0

    @classmethod
    def from_project_root(cls, project_root: Path | None = None) -> "Settings":
        root = (project_root or Path(__file__).resolve().parent.parent).resolve()
        data_dir = root / "data"
        os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(root / ".playwright-browsers"))
        return cls(project_root=root, data_dir=data_dir, index_path=data_dir / "index.sqlite3")

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)


settings = Settings.from_project_root()
