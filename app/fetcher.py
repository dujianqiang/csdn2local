from __future__ import annotations

import ssl
from dataclasses import dataclass
from http.client import IncompleteRead
from time import sleep
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urlsplit

from app.config import Settings


_MAX_ATTEMPTS = 3
_RETRY_DELAY_SECONDS = 1


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

    def fetch(self, url: str, *, referer: str | None = None) -> PageSnapshot:
        requested_url = self.validate_url(url)
        headers = {
            "User-Agent": self.settings.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Upgrade-Insecure-Requests": "1",
            "Cache-Control": "max-age=0",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin" if referer else "none",
            "Sec-Fetch-User": "?1",
        }
        if referer:
            headers["Referer"] = referer
        for attempt in range(_MAX_ATTEMPTS):
            request = Request(requested_url, headers=headers)
            try:
                with urlopen(request, timeout=self.settings.request_timeout_seconds) as response:
                    status_code = int(response.status)
                    final_url = str(response.geturl())
                    raw_content = response.read()
                    charset = response.headers.get_content_charset() or "utf-8"
                break
            except HTTPError as exc:
                exc.close()
                if exc.code != 521:
                    raise FetchError(f"文章请求失败：HTTP {exc.code}") from exc
                if exc.headers and exc.headers.get("Server", "").strip().casefold() == "waf":
                    raise FetchError("CSDN 安全防护拦截了此次请求（HTTP 521），请在浏览器中打开原网页确认。") from exc
                if attempt == _MAX_ATTEMPTS - 1:
                    raise FetchError(f"文章请求失败：HTTP 521（已尝试 {_MAX_ATTEMPTS} 次）") from exc
            except (OSError, IncompleteRead) as exc:
                reason = exc.reason if isinstance(exc, URLError) else exc
                disconnect = self._disconnect_message(reason)
                if disconnect is None:
                    raise FetchError(f"文章请求失败：{exc}") from exc
                if attempt == _MAX_ATTEMPTS - 1:
                    raise FetchError(
                        f"页面请求失败：{disconnect}，已尝试 {_MAX_ATTEMPTS} 次。请稍后重试。"
                    ) from exc
            sleep(_RETRY_DELAY_SECONDS)

        if status_code >= 400:
            raise FetchError(f"文章请求失败：HTTP {status_code}")
        html = raw_content.decode(charset, errors="replace")
        self.check_page_access(final_url, html)
        return PageSnapshot(requested_url=requested_url, final_url=final_url, html=html)

    @staticmethod
    def _disconnect_message(reason: object) -> str | None:
        if isinstance(reason, IncompleteRead):
            return "页面正文未接收完整"
        if isinstance(reason, (ConnectionAbortedError, ConnectionResetError)):
            return "页面连接提前断开"
        if isinstance(reason, ssl.SSLError) and (
            isinstance(reason, ssl.SSLEOFError) or getattr(reason, "reason", None) == "UNEXPECTED_EOF_WHILE_READING"
        ):
            return "HTTPS 连接提前断开"
        return None

    @staticmethod
    def check_page_access(final_url: str, html: str) -> None:
        final_hostname = (urlsplit(final_url).hostname or "").lower()
        if "passport" in final_hostname or "login" in final_hostname:
            raise FetchError("文章需要登录，第一阶段不支持登录文章")
        lowered = html.lower()
        if any(marker in lowered for marker in ("登录后查看", "请登录后阅读")):
            raise FetchError("文章需要登录或付费，第一阶段不支持此类文章")
