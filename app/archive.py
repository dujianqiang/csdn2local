from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from app.config import Settings
from app.fetcher import FetchError, PageFetcher
from app.index import ArticleIndex
from app.models import ArticleMetadata
from app.outputs import OutputError, write_html, write_pdf
from app.parser import ArticleParser
from app.resources import ResourceDownloader
from app.storage import ArchivePaths, ArchiveStore


class ArchiveFailure(RuntimeError):
    """An archive request could not produce any selected output."""


@dataclass
class ArchiveResult:
    status: str
    metadata: ArticleMetadata
    paths: ArchivePaths
    warnings: list[str] = field(default_factory=list)


class ArchiveService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.fetcher = PageFetcher(settings)
        self.parser = ArticleParser()
        self.resources = ResourceDownloader(settings)
        self.store = ArchiveStore(settings)
        self.index = ArticleIndex(settings.index_path)

    def archive(self, url: str, formats: list[str] | None = None) -> ArchiveResult:
        selected = self._normalize_formats(formats)
        snapshot = self.fetcher.fetch(url)
        parsed = self.parser.parse(snapshot.html, snapshot.final_url)
        metadata = parsed.metadata
        staging = self.store.create_staging()
        warnings: list[str] = []
        generated: list[str] = []
        try:
            staging.archive_dir.mkdir(parents=True, exist_ok=True)
            resource_result = self.resources.download(parsed.body_html, snapshot.final_url, staging.assets)
            warnings.extend(resource_result.warnings)
            body_html = resource_result.body_html
            if "html" in selected:
                try:
                    write_html(staging.html, metadata.title, body_html)
                    generated.append("html")
                except Exception as exc:
                    warnings.append(str(exc))
            if "pdf" in selected:
                try:
                    if not staging.html.exists():
                        write_html(staging.html, metadata.title, body_html)
                    write_pdf(staging.html, staging.pdf)
                    generated.append("pdf")
                    if "html" not in selected:
                        staging.html.unlink(missing_ok=True)
                except OutputError as exc:
                    warnings.append(str(exc))
            if not generated:
                raise ArchiveFailure("没有生成任何可用的归档文件：" + "；".join(warnings))
            metadata.formats = generated
            metadata.warnings = warnings
            self.store.write_metadata(staging, metadata)
            target = self.store.paths_for(metadata)
            old_archive = self.index.archive_dir_for_url(metadata.original_url)
            self.store.commit(staging, target)
            if old_archive and old_archive != target.archive_dir and old_archive.exists():
                shutil.rmtree(old_archive, ignore_errors=True)
            self.index.upsert(metadata, target)
            return ArchiveResult(
                status="partial" if warnings else "success",
                metadata=metadata,
                paths=target,
                warnings=warnings,
            )
        except Exception:
            self.store.cleanup_staging(staging)
            raise

    @staticmethod
    def _normalize_formats(formats: list[str] | None) -> list[str]:
        values = [value.lower().strip() for value in (formats or ["html"])]
        selected = list(dict.fromkeys(value for value in values if value in {"html", "pdf"}))
        if not selected:
            return ["html"]
        return selected
