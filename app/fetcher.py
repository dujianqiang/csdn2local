from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

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
        try:
            with httpx.Client(
                follow_redirects=True,
                timeout=self.settings.request_timeout_seconds,
                headers={
                    "User-Agent": "csdn2local/0.1 (+local article archiver)",
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                },
            ) as client:
                response = client.get(requested_url)
        except httpx.HTTPError as exc:
            raise FetchError(f"文章请求失败：{exc}") from exc

        if response.status_code >= 400:
            raise FetchError(f"文章请求失败：HTTP {response.status_code}")
        final_hostname = (urlsplit(str(response.url)).hostname or "").lower()
        if "passport" in final_hostname or "login" in final_hostname:
            raise FetchError("文章需要登录，第一阶段不支持登录文章")
        html = response.text
        lowered = html.lower()
        if any(marker in lowered for marker in ("登录后查看", "请登录后阅读", "付费专栏")):
            raise FetchError("文章需要登录或付费，第一阶段不支持此类文章")
        return PageSnapshot(requested_url=requested_url, final_url=str(response.url), html=html)
