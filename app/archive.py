from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock

from app.config import Settings
from app.fetcher import PageFetcher
from app.index import ArticleIndex
from app.markdown import write_markdown
from app.models import ArticleMetadata
from app.outputs import OutputError, write_html, write_pdf
from app.parser import ArticleParser, ParsedArticle
from app.resources import ResourceDownloader
from app.storage import ArchivePaths, ArchiveStore, normalize_url


class ArchiveFailure(RuntimeError):
    """An archive request could not produce any selected output."""


@dataclass
class PreparedArticle:
    metadata: ArticleMetadata
    body_html: str
    warnings: list[str]


@dataclass
class ArchiveResult:
    status: str
    metadata: ArticleMetadata
    paths: ArchivePaths
    warnings: list[str] = field(default_factory=list)


class ArchiveService:
    OUTPUT_FORMATS = ("html", "pdf", "md")

    def __init__(self, settings: Settings):
        self.settings = settings
        self.fetcher = PageFetcher(settings)
        self.parser = ArticleParser()
        self.resources = ResourceDownloader(settings)
        self.store = ArchiveStore(settings)
        self.index = ArticleIndex(settings.index_path, legacy_path=settings.data_dir / "index.sqlite3")
        self._publish_lock = Lock()

    def prepare_article(self, url: str, assets_dir: Path, *, referer: str | None = None) -> PreparedArticle:
        snapshot = self.fetcher.fetch(url, referer=referer)
        parsed = self.parser.parse(snapshot.html, snapshot.final_url)
        return self._localize_article(parsed, snapshot.final_url, assets_dir)

    def prepare_saved_article(self, url: str, html: str, assets_dir: Path) -> PreparedArticle:
        PageFetcher.check_page_access(url, html)
        parsed = self.parser.parse(html, url, saved_html=True)
        return self._localize_article(parsed, url, assets_dir)

    def _localize_article(self, parsed: ParsedArticle, url: str, assets_dir: Path) -> PreparedArticle:
        resources = self.resources.download(parsed.body_html, url, assets_dir)
        return PreparedArticle(parsed.metadata, resources.body_html, resources.warnings)

    def archive(self, url: str, formats: list[str] | None = None) -> ArchiveResult:
        selected = self._normalize_formats(formats)
        staging = self.store.create_staging()
        generated: list[str] = []
        try:
            staging.archive_dir.mkdir(parents=True, exist_ok=True)
            prepared = self.prepare_article(url, staging.assets)
            metadata = prepared.metadata
            warnings = list(prepared.warnings)
            body_html = prepared.body_html
            source_url = normalize_url(url)
            if "html" in selected:
                try:
                    write_html(staging.html, metadata.title, body_html, source_url=source_url)
                    generated.append("html")
                except Exception as exc:
                    staging.html.unlink(missing_ok=True)
                    warnings.append(str(exc))
            if "pdf" in selected:
                source_html = staging.html if "html" in generated else staging.archive_dir / "article-source.html"
                try:
                    if source_html != staging.html:
                        write_html(source_html, metadata.title, body_html, source_url=source_url)
                    write_pdf(source_html, staging.pdf)
                    generated.append("pdf")
                except OutputError as exc:
                    staging.pdf.unlink(missing_ok=True)
                    warnings.append(str(exc))
                finally:
                    if source_html != staging.html:
                        source_html.unlink(missing_ok=True)
            if "md" in selected:
                try:
                    write_markdown(staging.md, metadata.title, body_html, source_url=source_url)
                    generated.append("md")
                except Exception as exc:
                    staging.md.unlink(missing_ok=True)
                    warnings.append(f"Markdown 生成失败：{exc}")
            if not generated:
                raise ArchiveFailure("没有生成任何可用的归档文件：" + "；".join(warnings))
            metadata.warnings = warnings
            with self._publish_lock:
                target = self.store.paths_for(metadata)
                old_archive = self.index.archive_dir_for_url(metadata.original_url)
                root = self.settings.data_dir
                if old_archive and root in old_archive.parents and old_archive.resolve() == old_archive:
                    if old_archive.parent == root / "articles":
                        target = ArchivePaths(old_archive)
                self.store.retain_article_outputs(staging, target)
                if (
                    old_archive and old_archive != target.archive_dir
                    and old_archive.parent.parent == root and not old_archive.parent.name.startswith(".")
                    and old_archive.resolve() == old_archive
                ):
                    self.store.retain_article_outputs(staging, ArchivePaths(old_archive))
                metadata.formats = list(staging.article_outputs())
                self.store.write_metadata(staging, metadata)
                self.store.commit(staging, target)
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

    @classmethod
    def _normalize_formats(cls, formats: list[str] | None) -> list[str]:
        values = [value.lower().strip() for value in (formats or ["html"])]
        selected = list(dict.fromkeys(value for value in values if value in cls.OUTPUT_FORMATS))
        if not selected:
            return ["html"]
        return selected
