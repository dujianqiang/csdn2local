from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from app.config import Settings
from app.index import ArticleIndex
from app.models import ArticleMetadata
from app.storage import ArchivePaths, article_key, read_archive_aliases, topic_directory, topic_scope
from app.topic_history import list_topic_archives


@dataclass(frozen=True)
class ArchiveMove:
    source: Path
    destination: Path
    article: ArticleMetadata | None = None


def plan_migration(data_dir: Path) -> list[ArchiveMove]:
    root = data_dir.resolve()
    aliases = read_archive_aliases(root)
    reserved = {root / value for value in aliases.values()}
    moves = []

    def add(source: Path, proposed: Path, article: ArticleMetadata | None = None) -> None:
        previous = aliases.get(source.relative_to(root).as_posix())
        destination = root / previous if previous else proposed
        if not previous:
            copy_number = 2
            while destination.exists() or destination in reserved:
                destination = proposed.with_name(f"{proposed.name}-旧版-{copy_number}")
                copy_number += 1
        _check_path(root, source)
        _check_path(root, destination)
        expected_root = root / ("articles" if article else "topics")
        if expected_root not in destination.parents:
            raise ValueError(f"迁移目标不在归档目录：{destination}")
        reserved.add(destination)
        moves.append(ArchiveMove(source, destination, article))

    for path in sorted(root.glob("[!.]*/[!.]*/metadata.json")):
        source = path.parent
        if source.parent.name in {"articles", "topics"} or path.resolve() != path:
            continue
        if not any((source / f"article.{fmt}").is_file() for fmt in ("html", "pdf")):
            continue
        try:
            article = ArticleMetadata.from_dict(json.loads(path.read_text(encoding="utf-8")))
            if not article.original_url or not article.title:
                continue
            key = article_key(article.article_id, article.title, article.original_url)
        except (OSError, ValueError, TypeError, AttributeError):
            continue
        add(source, root / "articles" / key, article)

    topic_dirs: dict[str, Path] = {}
    for record in list_topic_archives(root):
        attempt = record.attempt
        source = attempt.target.archive_dir
        if len(source.relative_to(root).parts) != 3 or not attempt.topic_url:
            continue
        previous = aliases.get(source.relative_to(root).as_posix())
        if previous:
            topic_dirs[record.identity] = (root / previous).parent.parent
        elif record.identity not in topic_dirs:
            topic_dirs[record.identity] = topic_directory(root, attempt.topic_title, attempt.topic_url)
        add(source, topic_dirs[record.identity] / topic_scope(attempt.article_limit) / attempt.output_format)
    return moves


def migrate_archives(settings: Settings, moves: list[ArchiveMove]) -> None:
    root = settings.data_dir.resolve()
    internal = root / ".internal"
    backup = internal / "legacy"
    staging = internal / "staging"
    legacy_index = root / "index.sqlite3"
    alias_file = internal / "archive-aliases.json"
    aliases = read_archive_aliases(root)
    if not moves and not legacy_index.exists():
        return
    for path in (internal, backup, staging, alias_file, legacy_index, settings.index_path):
        _check_path(root, path)
    for move in moves:
        _check_path(root, move.source)
        _check_path(root, move.destination)
        original = backup / move.source.relative_to(root)
        _check_path(root, original)
        if original.exists():
            raise FileExistsError(f"原始归档备份已存在：{original}")
        aliases[move.source.relative_to(root).as_posix()] = move.destination.relative_to(root).as_posix()

    staging.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="migration-", dir=staging) as work:
        workspace = Path(work)
        pending_aliases = workspace / "archive-aliases.json"
        pending_aliases.write_text(json.dumps(aliases, ensure_ascii=False, indent=2), encoding="utf-8")
        pending_aliases.replace(alias_file)
        index = ArticleIndex(settings.index_path, legacy_path=legacy_index)
        for move in moves:
            source_contents = _contents(move.source)
            if not move.destination.exists():
                temporary = workspace / uuid4().hex
                shutil.copytree(move.source, temporary)
                if _contents(temporary) != source_contents:
                    raise OSError(f"复制校验失败：{move.source}")
                move.destination.parent.mkdir(parents=True, exist_ok=True)
                _check_path(root, move.destination)
                temporary.rename(move.destination)
            elif _contents(move.destination) != source_contents:
                raise FileExistsError(f"迁移目标已有不同内容：{move.destination}")
            if move.article:
                index.relocate(move.source, move.destination)
                if index.archive_dir_for_url(move.article.original_url) is None:
                    index.upsert(move.article, ArchivePaths(move.destination))
            original = backup / move.source.relative_to(root)
            original.parent.mkdir(parents=True, exist_ok=True)
            _check_path(root, move.source)
            _check_path(root, original)
            move.source.rename(original)
            for parent in move.source.parents:
                if parent == root or any(parent.iterdir()):
                    break
                parent.rmdir()

    if legacy_index.is_file() and legacy_index != settings.index_path:
        backup.mkdir(parents=True, exist_ok=True)
        for name in ("index.sqlite3", "index.sqlite3-wal", "index.sqlite3-shm", "index.sqlite3-journal"):
            source, destination = root / name, backup / name
            if source.is_file():
                _check_path(root, source)
                _check_path(root, destination)
                if destination.exists():
                    raise FileExistsError(f"原始索引备份已存在：{destination}")
                source.rename(destination)
    old_staging = root / ".staging"
    if old_staging.is_dir() and old_staging.resolve() == old_staging and not any(old_staging.iterdir()):
        old_staging.rmdir()


def _check_path(root: Path, path: Path) -> None:
    if root not in path.parents or path.resolve() != path:
        raise ValueError(f"路径不在数据目录内，或经过链接：{path}")


def _contents(directory: Path) -> dict[str, str]:
    contents = {}
    for path in directory.rglob("*"):
        _check_path(directory, path)
        if path.is_dir():
            contents[path.relative_to(directory).as_posix()] = ""
        elif path.is_file():
            with path.open("rb") as file:
                contents[path.relative_to(directory).as_posix()] = hashlib.file_digest(file, "sha256").hexdigest()
        else:
            raise ValueError(f"无法迁移此文件：{path}")
    return contents


def main() -> None:
    parser = argparse.ArgumentParser(description="整理已有单篇与专题归档。")
    parser.add_argument("--apply", action="store_true", help="服务停止后执行迁移，默认只预览。")
    args = parser.parse_args()
    settings = Settings.from_project_root()
    moves = plan_migration(settings.data_dir)
    for move in moves:
        print(f"{move.source.relative_to(settings.data_dir)} → {move.destination.relative_to(settings.data_dir)}")
    if args.apply:
        migrate_archives(settings, moves)
        print(f"已迁移 {len(moves)} 份归档。")
    else:
        print(f"预览：{len(moves)} 份归档。")


if __name__ == "__main__":
    main()
