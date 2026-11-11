from __future__ import annotations

import ssl
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urlsplit

from app.config import Settings


class FetchError(RuntimeError):
    """An article page could not be fetched or is outside the supported scope."""


@dataclass(frozen=True)
class PageSnapshot:
    requested_url: str
    final_url: str
    html: str


class PageFetcher:
    def __init__(self, settings: Settings):
        self.settings = settings

    @staticmethod
    def validate_url(url: str) -> str:
        parsed = urlsplit(url.strip())
        hostname = (parsed.hostname or "").lower()
        if parsed.scheme not in {"http", "https"} or not hostname:
            raise FetchError("请输入有效的 HTTP/HTTPS 文章地址")
        if hostname != "csdn.net" and not hostname.endswith(".csdn.net"):
            raise FetchError("第一阶段只支持 CSDN 文章地址")
        return url.strip()

    def fetch(self, url: str) -> PageSnapshot:
        requested_url = self.validate_url(url)
        request = Request(
            requested_url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Upgrade-Insecure-Requests": "1",
            },
        )
        try:
            with urlopen(request, timeout=self.settings.request_timeout_seconds) as response:
                status_code = int(response.status)
                final_url = str(response.geturl())
                raw_content = response.read()
                charset = response.headers.get_content_charset() or "utf-8"
        except HTTPError as exc:
            raise FetchError(f"文章请求失败：HTTP {exc.code}") from exc
        except (URLError, TimeoutError, ssl.SSLError, OSError) as exc:
            raise FetchError(f"文章请求失败：{exc}") from exc

        if status_code >= 400:
            raise FetchError(f"文章请求失败：HTTP {status_code}")
        final_hostname = (urlsplit(final_url).hostname or "").lower()
        if "passport" in final_hostname or "login" in final_hostname:
            raise FetchError("文章需要登录，第一阶段不支持登录文章")
        html = raw_content.decode(charset, errors="replace")
        lowered = html.lower()
        if any(marker in lowered for marker in ("登录后查看", "请登录后阅读")):
            raise FetchError("文章需要登录或付费，第一阶段不支持此类文章")
        return PageSnapshot(requested_url=requested_url, final_url=final_url, html=html)
