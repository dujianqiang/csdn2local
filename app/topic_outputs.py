from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any, Iterable
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

from app.parser import CODE_PRINT_CSS, render_source_url, wrap_code_blocks


TOPIC_CSS = """
body { max-width: 900px; margin: 2rem auto; padding: 0 1rem; line-height: 1.7; color: #222; }
img, video { max-width: 100%; height: auto; }
nav.topic-navigation { padding: 1rem 1.25rem; margin-bottom: 2rem; background: #f5f7fa; border: 1px solid #d9e0e8; border-radius: 8px; }
nav.topic-navigation ol { margin: .5rem 0 0; padding-left: 1.5rem; }
section.topic-article { margin: 2.5rem 0; padding-top: 1rem; border-top: 2px solid #e5e7eb; }
.archive-source { overflow-wrap: anywhere; }
nav.topic-navigation .archive-source { margin: 0; }
pre { overflow-x: auto; margin: 1.25rem 0; padding: 1rem 1.25rem; background: #282c34; color: #abb2bf; border: 1px solid #3b4048; border-radius: 8px; line-height: 1.6; white-space: pre; tab-size: 4; font-family: Consolas, "Cascadia Code", "Courier New", monospace; }
pre code { display: block; padding: 0; background: transparent; color: inherit; white-space: pre; font-family: inherit; }
pre .token.comment { color: #7f848e; }
details.code-block { margin: 1.25rem 0; background: #282c34; border: 1px solid #3b4048; border-radius: 8px; overflow: hidden; }
details.code-block > summary { cursor: pointer; padding: .55rem 1rem; background: #21252b; color: #abb2bf; font: 600 0.9rem/1.4 Consolas, "Cascadia Code", "Courier New", monospace; user-select: none; }
details.code-block[open] > summary { border-bottom: 1px solid #3b4048; }
details.code-block pre { margin: 0; border: 0; border-radius: 0; }
@media print { nav.topic-navigation a { color: #000; text-decoration: none; } }
""".strip() + "\n" + CODE_PRINT_CSS


def render_topic_document(title: str, articles: Iterable[dict[str, Any]], *, source_url: str = "") -> str:
    entries = list(articles)
    navigation: list[str] = []
    sections: list[str] = []
    for article in entries:
        position = int(article["position"])
        article_title = str(article.get("title") or f"文章 {position}")
        anchor = f"article-{position}"
        source_note = render_source_url(str(article.get("url") or ""))
        error = article.get("error")
        if error:
            navigation.append(f"<li>{escape(article_title)}（下载失败：{escape(str(error))}）{source_note}</li>")
            continue
        navigation.append(f'<li><a href="#{anchor}">{escape(article_title)}</a></li>')
        sections.append(
            f'<section class="topic-article" id="{anchor}">'
            f"<h2>{escape(article_title)}</h2>"
            f"{source_note}"
            f"{wrap_code_blocks(str(article.get('body_html') or ''))}"
            f"</section>"
        )
    navigation_html = "\n".join(navigation)
    sections_html = "\n".join(sections)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="generator" content="csdn2local-topic">
  <title>{escape(title)}</title>
  <style>{TOPIC_CSS}</style>
</head>
<body>
  <header><h1>{escape(title)}</h1>{render_source_url(source_url)}</header>
  <nav class="topic-navigation" aria-label="专题导航">
    <strong>专题导航</strong>
    <ol>{navigation_html}</ol>
  </nav>
  <main>{sections_html}</main>
</body>
</html>
"""


def write_topic_html(path: Path, title: str, articles: Iterable[dict[str, Any]], *, source_url: str = "") -> None:
    path.write_text(render_topic_document(title, articles, source_url=source_url), encoding="utf-8")


def write_topic_epub(
    path: Path, title: str, articles: Iterable[dict[str, Any]], assets: Iterable[Path], *, source_url: str = ""
) -> None:
    entries = list(articles)
    content = render_topic_document(title, entries, source_url=source_url).replace('href="#', 'href="content.xhtml#')
    nav_items = []
    for article in entries:
        if article.get("error"):
            continue
        position = int(article["position"])
        article_title = escape(str(article.get("title") or f"文章 {position}"))
        nav_items.append(f'<li><a href="content.xhtml#article-{position}">{article_title}</a></li>')
    nav = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="zh-CN">
<head><title>专题导航</title></head>
<body><nav epub:type="toc" id="toc"><h1>专题导航</h1><ol>""" + "".join(nav_items) + """</ol></nav></body>
</html>"""
    container = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="OEBPS/package.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>"""
    manifest_assets = []
    asset_entries = list(assets)
    for index, asset in enumerate(asset_entries):
        name = asset.name
        media_type = _media_type(asset)
        manifest_assets.append(f'<item id="asset-{index}" href="assets/{escape(name)}" media-type="{media_type}"/>')
    manifest = "\n    ".join(manifest_assets)
    package = f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="book-id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="book-id">csdn-topic</dc:identifier><dc:title>{escape(title)}</dc:title><dc:language>zh-CN</dc:language></metadata>
  <manifest>
    <item id="nav" properties="nav" href="nav.xhtml" media-type="application/xhtml+xml"/>
    <item id="content" href="content.xhtml" media-type="application/xhtml+xml"/>
    <item id="css" href="styles.css" media-type="text/css"/>
    {manifest}
  </manifest>
  <spine><itemref idref="content"/></spine>
</package>"""
    with ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip", compress_type=ZIP_STORED)
        archive.writestr("META-INF/container.xml", container, compress_type=ZIP_DEFLATED)
        archive.writestr("OEBPS/package.opf", package, compress_type=ZIP_DEFLATED)
        archive.writestr("OEBPS/nav.xhtml", nav, compress_type=ZIP_DEFLATED)
        archive.writestr("OEBPS/content.xhtml", content, compress_type=ZIP_DEFLATED)
        archive.writestr("OEBPS/styles.css", TOPIC_CSS, compress_type=ZIP_DEFLATED)
        for asset in asset_entries:
            archive.write(asset, f"OEBPS/assets/{asset.name}")


def _media_type(path: Path) -> str:
    suffix = path.suffix.lower()
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".svg": "image/svg+xml",
    }.get(suffix, "application/octet-stream")
