from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.topic import TopicService


@dataclass(frozen=True)
class TopicArchive:
    title: str
    output_format: str
    output_path: Path
    saved_at: datetime
    preview: bool


def list_topic_archives(data_dir: Path) -> list[TopicArchive]:
    records = []
    for metadata_path in data_dir.resolve().glob("[!.]*/topics/[!.]*/metadata.json"):
        try:
            if metadata_path.resolve() != metadata_path or not metadata_path.is_file():
                continue
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if not isinstance(metadata, dict):
                continue
            title = metadata.get("title")
            output_format = metadata.get("format")
            if not isinstance(title, str) or not title.strip():
                continue
            if not isinstance(output_format, str) or output_format not in TopicService.OUTPUT_FORMATS:
                continue
            output_path = metadata_path.with_name(f"topic.{output_format}")
            if output_path.resolve() != output_path or not output_path.is_file():
                continue
            saved_at = datetime.fromtimestamp(output_path.stat().st_mtime).astimezone()
        except (OSError, RuntimeError, ValueError, OverflowError):
            # An archive may be removed or replaced while the history is being read.
            continue
        limit = metadata.get("article_limit")
        preview = metadata_path.parent.name.startswith("preview-") or (isinstance(limit, int) and limit > 0)
        records.append(TopicArchive(title.strip(), output_format, output_path, saved_at, preview))
    return sorted(records, key=lambda record: (record.saved_at, record.output_path), reverse=True)
