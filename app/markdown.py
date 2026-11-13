from __future__ import annotations

import re
from pathlib import Path
from typing import Any, BinaryIO, Iterable
from urllib.parse import quote, urlsplit
from zipfile import ZIP_DEFLATED, ZipFile

from bs4 import BeautifulSoup
from markdownify import MarkdownConverter


class ArticleMarkdownConverter(MarkdownConverter):
    def convert_pre(self, el, text, parent_tags):
        if not text:
            return ""
        classes = el.get("class", [])
        code = el.find("code")
        if code is not None:
            classes = [*code.get("class", []), *classes]
        language = next(
            (name.removeprefix("language-") for name in classes if re.fullmatch(r"language-[\w+-]+", name)),
            "",
        )
        longest = max(map(len, re.findall(r"`+", text)), default=0)
        fence = "`" * max(3, longest + 1)
        content = text if text.endswith("\n") else text + "\n"
        return f"\n\n{fence}{language}\n{content}{fence}\n\n"

    def convert_hN(self, n, el, text, parent_tags):
        return super().convert_hN(min(n + self.options["heading_offset"], 6), el, text, parent_tags)


def _markdown_text(text: str) -> str:
    text = " ".join(text.split())
    return re.sub(r"([\\`*_\[\]<>#&])", r"\\\1", text)


def _destination(value: str) -> str:
    try:
        scheme = urlsplit(value).scheme.lower()
    except ValueError:
        return ""
    if scheme not in {"", "http", "https", "mailto"}:
        return ""
    return quote(value, safe=":/?#[]@!$&'*+,;=%")


def _markdown_body(body_html: str, *, heading_offset: int) -> str:
    soup = BeautifulSoup(body_html, "lxml")
    for node in soup.select("a[href], [src], [poster]"):
        for attribute in ("href", "src", "poster"):
            value = node.get(attribute)
            if value:
                destination = _destination(value)
                if destination:
                    node[attribute] = destination
                else:
                    del node[attribute]
    for image in soup.find_all("img"):
        image["alt"] = _markdown_text(image.get("alt", ""))
        if not image.get("src"):
            image.replace_with(image.get("alt", ""))
    converter = ArticleMarkdownConverter(
        heading_style="ATX", heading_offset=heading_offset, escape_misc=True,
        autolinks=False, keep_inline_images_in=["a", "th", "td"], table_infer_header=True,
    )
    return converter.convert_soup(soup).strip()


def _source_note(source_url: str) -> str:
    destination = _destination(source_url)
    return f"原始 URL：[{_markdown_text(source_url)}]({destination})" if destination else ""


def write_markdown(path: Path, title: str, body_html: str, *, source_url: str = "") -> None:
    parts = [f"# {_markdown_text(title)}", _source_note(source_url), _markdown_body(body_html, heading_offset=1)]
    path.write_text("\n\n".join(filter(None, parts)) + "\n", encoding="utf-8", newline="\n")


def write_markdown_bundle(document: Path, output: BinaryIO) -> None:
    assets = document.parent / "assets"
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as bundle:
        bundle.write(document, document.name)
        if assets.is_symlink() or assets.resolve() != assets or not assets.is_dir():
            return
        for asset in sorted(assets.iterdir()):
            if not asset.name.startswith(".") and not asset.is_symlink() and asset.is_file():
                bundle.write(asset, f"assets/{asset.name}")


def write_topic_markdown(path: Path, title: str, articles: Iterable[dict[str, Any]], *, source_url: str = "") -> None:
    navigation = []
    sections = []
    for article in articles:
        position = int(article["position"])
        article_title = _markdown_text(article["title"])
        anchor = f"article-{position}"
        navigation.append(f"{position}. [{article_title}](#{anchor})")
        source_note = _source_note(article["url"])
        if article["error"]:
            detail = _markdown_text(str(article["error"]))
            body = f"下载失败：{detail}"
        else:
            body = _markdown_body(article["body_html"], heading_offset=2)
        sections.append("\n\n".join(filter(None, [f'<a id="{anchor}"></a>', f"## {article_title}", source_note, body])))
    parts = [f"# {_markdown_text(title)}", _source_note(source_url), "## 专题目录", "\n".join(navigation), *sections]
    path.write_text("\n\n".join(filter(None, parts)) + "\n", encoding="utf-8", newline="\n")
