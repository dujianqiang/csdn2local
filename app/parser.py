from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup, Tag

from app.models import ArticleMetadata
from app.storage import normalize_url


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
        ".comment",
        "[class*='comment']",
        "[id*='comment']",
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

    def parse(self, html: str, source_url: str) -> ParsedArticle:
        soup = BeautifulSoup(html, "lxml")
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


def render_article_document(title: str, body_html: str) -> str:
    generated_at = datetime.now(timezone.utc).isoformat()
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
    img, video {{ max-width: 100%; height: auto; }}
    pre {{ overflow-x: auto; padding: 1rem; background: #f6f8fa; }}
    code {{ font-family: Consolas, monospace; }}
  </style>
</head>
<body>
  <article>
    <h1>{escape(title)}</h1>
    {body_html}
  </article>
</body>
</html>
"""
