from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup, Tag

from app.models import ArticleMetadata
from app.storage import normalize_url


CODE_PRINT_CSS = """
@media print {
  details.code-block { border: 0; overflow: visible; }
  details.code-block > summary { display: none; }
  details.code-block::details-content { content-visibility: visible; }
  details.code-block > pre { border-radius: 8px; }
  pre, pre code { white-space: pre-wrap; overflow-wrap: anywhere; overflow: visible; }
}
""".strip()


@dataclass
class ParsedArticle:
    metadata: ArticleMetadata
    body_html: str
    resource_urls: list[str]


class ArticleParser:
    BODY_SELECTORS = (
        "#content_views",
        ".article_content",
        ".blog-content-box .article_content",
        ".article-body",
        "article",
    )
    REMOVE_SELECTORS = (
        "script",
        "style",
        "noscript",
        "iframe",
        "nav",
        "header",
        "footer",
        "aside",
        "div.comment-box",
        "div.comment-list",
        "div.comment-list-box",
        "div.comment-area",
        "div.comment-container",
        "section.comment",
        "section.comment-box",
        "#comment",
        "#comment-box",
        "#comment-list",
        "#commentList",
        "[id^='comment-']",
        ".recommend",
        "[class*='recommend']",
        ".sidebar",
        ".aside",
        ".toolbar",
        ".hide-article-box",
        ".login-box",
        ".adsbygoogle",
        "[class*='advert']",
        "[id*='advert']",
    )

    def parse(self, html: str, source_url: str, *, saved_html: bool = False) -> ParsedArticle:
        soup = BeautifulSoup(html, "lxml")
        if saved_html:
            expected_id = self._article_id(source_url, soup)
            canonical = soup.select_one("link[rel~=canonical][href]")
            if canonical is not None:
                canonical_path = urlsplit(str(canonical["href"])).path
                declared_id = re.search(r"/article/details/(\d+)(?:/|$)", canonical_path)
                if declared_id and declared_id.group(1) != expected_id:
                    raise ValueError("HTML 中的原文地址与文件名中的文章 ID 不一致")
            body = soup.select_one("#content_views, .article_content, .article-body")
            if body is not None:
                for node in body.select("base, meta, link, object, embed, form"):
                    node.decompose()
                if not body.get_text(strip=True) and not body.select_one("img, video, audio"):
                    body = None
        else:
            body = self._find_body(soup)
        if body is None:
            raise ValueError("未找到 CSDN 文章正文")
        for selector in self.REMOVE_SELECTORS:
            for node in body.select(selector):
                node.decompose()
        self._sanitize_nodes(body)
        title = self._first_content(
            soup.select_one("meta[property='og:title']"),
            soup.select_one("h1.title-article"),
            soup.select_one("h1.article-title"),
            body.select_one("h1"),
            soup.title,
        ) or "未命名文章"
        parsed_url = urlsplit(source_url)
        domain = (parsed_url.hostname or "").lower()
        article_id = self._article_id(source_url, soup)
        metadata = ArticleMetadata(
            title=title.strip(),
            original_url=normalize_url(source_url),
            domain=domain,
            article_id=article_id,
            author=self._metadata_value(soup, ("author", "user-name", "follow-nickName")),
            published_at=self._metadata_value(soup, ("article:published_time", "datePublished", "publish-time")),
            tags=self._tags(soup),
        )
        body_html = "".join(str(child) for child in body.contents).strip()
        resource_urls = self._resource_urls(body_html, source_url)
        return ParsedArticle(metadata=metadata, body_html=body_html, resource_urls=resource_urls)

    def _find_body(self, soup: BeautifulSoup) -> Tag | None:
        for selector in self.BODY_SELECTORS:
            candidate = soup.select_one(selector)
            if candidate and len(candidate.get_text(" ", strip=True)) >= 40:
                return candidate
        candidates = soup.find_all(["div", "main", "section"])
        scored = [(self._body_score(candidate), candidate) for candidate in candidates]
        scored.sort(key=lambda item: item[0], reverse=True)
        return scored[0][1] if scored and scored[0][0] > 0 else None

    @staticmethod
    def _body_score(candidate: Tag) -> float:
        text_length = len(candidate.get_text(" ", strip=True))
        if text_length < 40:
            return 0
        links = len(candidate.find_all("a"))
        return text_length - links * 18

    @staticmethod
    def _sanitize_nodes(body: Tag) -> None:
        for node in body.find_all(True):
            for name in list(node.attrs):
                if name.lower().startswith("on"):
                    del node.attrs[name]
            for attr in ("href", "src"):
                value = node.get(attr)
                if isinstance(value, str) and value.strip().lower().startswith("javascript:"):
                    del node.attrs[attr]

    @staticmethod
    def _first_content(*nodes: Tag | None) -> str | None:
        for node in nodes:
            if not node:
                continue
            if node.name == "meta":
                value = node.get("content")
            else:
                value = node.get_text(" ", strip=True)
            if value:
                return value
        return None

    def _metadata_value(self, soup: BeautifulSoup, names: tuple[str, ...]) -> str | None:
        for name in names:
            meta = soup.select_one(f"meta[name='{name}'], meta[property='{name}']")
            value = self._first_content(meta)
            if value:
                return value
            if re.fullmatch(r"[A-Za-z0-9_-]+", name):
                node = soup.select_one(f".{name}, #{name}")
                value = self._first_content(node)
                if value:
                    return value
        return None

    @staticmethod
    def _article_id(source_url: str, soup: BeautifulSoup) -> str | None:
        match = re.search(r"/article/details/(\d+)", source_url)
        if match:
            return match.group(1)
        for key in ("article-id", "articleId", "post-id"):
            node = soup.select_one(f"meta[name='{key}'], [data-{key.lower()}]")
            if node:
                return node.get("content") or node.get(f"data-{key.lower()}")
        return None

    @staticmethod
    def _tags(soup: BeautifulSoup) -> list[str]:
        keywords = soup.select_one("meta[name='keywords']")
        if keywords and keywords.get("content"):
            return [tag.strip() for tag in keywords["content"].replace("，", ",").split(",") if tag.strip()]
        return [tag.get_text(" ", strip=True) for tag in soup.select(".tag-link, .tags a") if tag.get_text(strip=True)]

    @staticmethod
    def _resource_urls(body_html: str, source_url: str) -> list[str]:
        soup = BeautifulSoup(body_html, "lxml")
        urls: list[str] = []
        for node in soup.find_all(["img", "source", "video", "audio"]):
            raw = node.get("src") or node.get("data-src") or node.get("srcset")
            if not raw:
                continue
            first = str(raw).split(",")[0].strip().split(" ")[0]
            absolute = urljoin(source_url, first)
            if urlsplit(absolute).scheme in {"http", "https"} and absolute not in urls:
                urls.append(absolute)
        return urls


def render_source_url(source_url: str) -> str:
    if not source_url:
        return ""
    url = escape(source_url)
    return f'<p class="archive-source">原始 URL：<a href="{url}">{url}</a></p>'


def render_article_document(title: str, body_html: str, *, source_url: str = "") -> str:
    generated_at = datetime.now(timezone.utc).isoformat()
    body_html = wrap_code_blocks(body_html)
    return f"""<!doctype html>
<html lang=\"zh-CN\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <meta name=\"generator\" content=\"csdn2local\">
  <meta name=\"saved-at\" content=\"{escape(generated_at)}\">
  <title>{escape(title)}</title>
  <style>
    body {{ max-width: 900px; margin: 2rem auto; padding: 0 1rem; line-height: 1.7; color: #222; }}
    .archive-source {{ overflow-wrap: anywhere; }}
    img, video {{ max-width: 100%; height: auto; }}
    pre {{ overflow-x: auto; margin: 1.25rem 0; padding: 1rem 1.25rem; background: #282c34; color: #abb2bf; border: 1px solid #3b4048; border-radius: 8px; line-height: 1.6; white-space: pre; tab-size: 4; font-family: Consolas, "Cascadia Code", "Courier New", monospace; }}
    pre code {{ display: block; padding: 0; background: transparent; color: inherit; white-space: pre; font-family: inherit; }}
    pre .token.comment {{ color: #7f848e; }}
    details.code-block {{ margin: 1.25rem 0; background: #282c34; border: 1px solid #3b4048; border-radius: 8px; overflow: hidden; }}
    details.code-block > summary {{ cursor: pointer; padding: .55rem 1rem; background: #21252b; color: #abb2bf; font: 600 0.9rem/1.4 Consolas, "Cascadia Code", "Courier New", monospace; user-select: none; }}
    details.code-block[open] > summary {{ border-bottom: 1px solid #3b4048; }}
    details.code-block pre {{ margin: 0; border: 0; border-radius: 0; }}
    {CODE_PRINT_CSS}
  </style>
</head>
<body>
  <article>
    <h1>{escape(title)}</h1>
    {render_source_url(source_url)}
    {body_html}
  </article>
</body>
</html>
"""


def wrap_code_blocks(body_html: str) -> str:
    soup = BeautifulSoup(body_html, "lxml")
    root = soup.body or soup
    for index, pre in enumerate(root.find_all("pre"), start=1):
        details = soup.new_tag("details", attrs={"class": "code-block"})
        summary = soup.new_tag("summary")
        summary.string = f"代码块 {index}"
        pre.replace_with(details)
        details.append(summary)
        details.append(pre)
    return "".join(str(child) for child in root.contents)
