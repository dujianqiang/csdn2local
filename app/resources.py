from __future__ import annotations

import hashlib
import mimetypes
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup

from app.config import Settings
from app.storage import sanitize_filename


class ResourceDownloadResult:
    def __init__(self, body_html: str, warnings: list[str]):
        self.body_html = body_html
        self.warnings = warnings


class ResourceDownloader:
    def __init__(self, settings: Settings):
        self.settings = settings

    def download(self, body_html: str, source_url: str, assets_dir: Path) -> ResourceDownloadResult:
        assets_dir.mkdir(parents=True, exist_ok=True)
        soup = BeautifulSoup(body_html, "lxml")
        warnings: list[str] = []
        downloaded: dict[str, str] = {}
        used_names: set[str] = set()
        with httpx.Client(
            follow_redirects=True,
            timeout=self.settings.request_timeout_seconds,
            headers={"User-Agent": "csdn2local/0.1 (+local article archiver)", "Referer": source_url},
        ) as client:
            for node in soup.find_all(["img", "source", "video", "audio"]):
                raw = node.get("src") or node.get("data-src") or node.get("srcset")
                if not raw:
                    continue
                original = str(raw).split(",")[0].strip().split(" ")[0]
                absolute = urljoin(source_url, original)
                if not absolute.startswith(("http://", "https://")):
                    continue
                if absolute in downloaded:
                    local_name = downloaded[absolute]
                    node["src"] = f"assets/{local_name}"
                    node.attrs.pop("data-src", None)
                    node.attrs.pop("srcset", None)
                    continue
                try:
                    response = client.get(absolute)
                    response.raise_for_status()
                    filename = self._filename(absolute, response.headers.get("content-type"), used_names)
                    (assets_dir / filename).write_bytes(response.content)
                    downloaded[absolute] = filename
                    node["src"] = f"assets/{filename}"
                    node.attrs.pop("data-src", None)
                    node.attrs.pop("srcset", None)
                except (httpx.HTTPError, OSError) as exc:
                    warnings.append(f"资源下载失败：{absolute}（{exc}）")
                    node["data-csdn2local-missing"] = "true"
        return ResourceDownloadResult("".join(str(child) for child in soup.contents), warnings)

    @staticmethod
    def _filename(url: str, content_type: str | None, used_names: set[str]) -> str:
        path_name = Path(urlsplit(url).path).name
        suffix = Path(path_name).suffix
        if not suffix and content_type:
            suffix = mimetypes.guess_extension(content_type.split(";", 1)[0].strip()) or ""
        stem = sanitize_filename(Path(path_name).stem or "asset", max_length=70, fallback="asset")
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:10]
        candidate = f"{stem}-{digest}{suffix.lower()}"
        used_names.add(candidate)
        return candidate
