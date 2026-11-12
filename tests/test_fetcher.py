from __future__ import annotations

import io
import ssl
from email.message import Message
from unittest.mock import Mock
from urllib.error import HTTPError, URLError

import pytest

from app.config import Settings
from app.fetcher import FetchError, PageFetcher


URL = "https://blog.csdn.net/sinat_27016095/article/details/148428154"
TOPIC_URL = "https://blog.csdn.net/demo/category_123.html"


class FakeResponse:
    status = 200
    headers = Message()

    def __init__(self, content: bytes, url: str = URL):
        self.content = content
        self.url = url

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def geturl(self):
        return self.url

    def read(self):
        return self.content


def test_hidden_generic_recharge_component_does_not_reject_public_page(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "app.fetcher.urlopen",
        lambda *_args, **_kwargs: FakeResponse(b"<div class='pay-code-content'>\xe4\xbb\x98\xe8\xb4\xb9\xe4\xb8\x93\xe6\xa0\x8f</div><div id='content_views'>\xe5\x85\xac\xe5\xbc\x80\xe6\xad\xa3\xe6\x96\x87</div>"),
    )

    snapshot = PageFetcher(Settings.from_project_root(tmp_path)).fetch(URL)

    assert "公开正文" in snapshot.html


def test_fetch_uses_browser_navigation_headers_and_optional_topic_referer(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(
        "CSDN2LOCAL_USER_AGENT",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/157.0.0.0 Safari/537.36",
    )
    open_page = Mock(side_effect=[FakeResponse(b"<p>with topic context</p>"), FakeResponse(b"<p>single</p>")])
    monkeypatch.setattr("app.fetcher.urlopen", open_page)
    fetcher = PageFetcher(Settings.from_project_root(tmp_path))

    fetcher.fetch(URL, referer=TOPIC_URL)
    topic_request = open_page.call_args_list[0].args[0]
    assert topic_request.get_header("User-agent").endswith("Chrome/157.0.0.0 Safari/537.36")
    assert topic_request.get_header("Sec-fetch-dest") == "document"
    assert topic_request.get_header("Sec-fetch-mode") == "navigate"
    assert topic_request.get_header("Sec-fetch-site") == "same-origin"
    assert topic_request.get_header("Sec-fetch-user") == "?1"
    assert topic_request.get_header("Referer") == TOPIC_URL

    fetcher.fetch(URL)
    single_request = open_page.call_args_list[1].args[0]
    assert single_request.get_header("Sec-fetch-site") == "none"
    assert single_request.get_header("Referer") is None


@pytest.mark.parametrize("marker", ["登录后查看", "请登录后阅读"])
def test_explicit_access_message_is_rejected(monkeypatch, tmp_path, marker: str) -> None:
    monkeypatch.setattr("app.fetcher.urlopen", lambda *_args, **_kwargs: FakeResponse(f"<p>{marker}</p>".encode()))

    with pytest.raises(FetchError, match="登录或付费"):
        PageFetcher(Settings.from_project_root(tmp_path)).fetch(URL)


def test_http_error_is_reported_without_retry(monkeypatch, tmp_path) -> None:
    error = HTTPError(URL, 404, "Not found", Message(), io.BytesIO())
    open_page = Mock(side_effect=error)
    monkeypatch.setattr("app.fetcher.urlopen", open_page)

    with pytest.raises(FetchError, match="HTTP 404"):
        PageFetcher(Settings.from_project_root(tmp_path)).fetch(URL)
    open_page.assert_called_once()


def test_retries_http_521_and_reads_next_response(monkeypatch, tmp_path) -> None:
    error_body = io.BytesIO()
    error = HTTPError(URL, 521, "Origin unavailable", Message(), error_body)
    open_page = Mock(side_effect=[error, FakeResponse(b"<p>Article available</p>")])
    pause = Mock()
    monkeypatch.setattr("app.fetcher.urlopen", open_page)
    monkeypatch.setattr("app.fetcher.sleep", pause)

    assert PageFetcher(Settings.from_project_root(tmp_path)).fetch(URL).html == "<p>Article available</p>"
    assert error_body.closed
    assert open_page.call_count == 2
    pause.assert_called_once_with(0.25)


def test_reports_persistent_http_521_after_three_attempts(monkeypatch, tmp_path) -> None:
    errors = [HTTPError(URL, 521, "Origin unavailable", Message(), io.BytesIO()) for _ in range(3)]
    open_page = Mock(side_effect=errors)
    pause = Mock()
    monkeypatch.setattr("app.fetcher.urlopen", open_page)
    monkeypatch.setattr("app.fetcher.sleep", pause)

    with pytest.raises(FetchError, match="HTTP 521（已尝试 3 次）") as failure:
        PageFetcher(Settings.from_project_root(tmp_path)).fetch(URL)

    assert failure.value.__cause__ is errors[-1]
    assert open_page.call_count == 3
    assert [call.args[0] for call in pause.call_args_list] == [0.25, 0.5]


def test_reports_waf_521_without_retrying(monkeypatch, tmp_path) -> None:
    headers = Message()
    headers["Server"] = "WAF"
    body = io.BytesIO()
    error = HTTPError(URL, 521, "Blocked", headers, body)
    open_page = Mock(side_effect=error)
    pause = Mock()
    monkeypatch.setattr("app.fetcher.urlopen", open_page)
    monkeypatch.setattr("app.fetcher.sleep", pause)

    with pytest.raises(FetchError, match="安全防护拦截.*HTTP 521") as failure:
        PageFetcher(Settings.from_project_root(tmp_path)).fetch(URL)

    assert failure.value.__cause__ is error
    assert body.closed
    open_page.assert_called_once()
    pause.assert_not_called()


def test_retries_wrapped_tls_eof_when_opening_a_topic(monkeypatch, tmp_path) -> None:
    topic_url = "https://blog.csdn.net/demo/category_123.html"
    eof = ssl.SSLError("Unexpected EOF")
    eof.reason = "UNEXPECTED_EOF_WHILE_READING"
    open_page = Mock(side_effect=[URLError(eof), FakeResponse(b"<h1>Topic</h1>", topic_url)])
    pause = Mock()
    monkeypatch.setattr("app.fetcher.urlopen", open_page)
    monkeypatch.setattr("app.fetcher.sleep", pause)

    snapshot = PageFetcher(Settings.from_project_root(tmp_path)).fetch(topic_url)

    assert snapshot.html == "<h1>Topic</h1>"
    assert [call.args[0].full_url for call in open_page.call_args_list] == [topic_url, topic_url]
    pause.assert_called_once_with(0.25)


def test_retries_tls_eof_during_body_read(monkeypatch, tmp_path) -> None:
    response = FakeResponse(b"")
    response.read = Mock(side_effect=ssl.SSLEOFError("Unexpected EOF"))
    open_page = Mock(side_effect=[response, FakeResponse(b"<p>Complete article</p>")])
    monkeypatch.setattr("app.fetcher.urlopen", open_page)
    monkeypatch.setattr("app.fetcher.sleep", Mock())

    snapshot = PageFetcher(Settings.from_project_root(tmp_path)).fetch(URL)

    assert snapshot.html == "<p>Complete article</p>"
    assert open_page.call_count == 2


def test_reports_tls_eof_after_three_attempts(monkeypatch, tmp_path) -> None:
    error = URLError(ssl.SSLEOFError("Unexpected EOF"))
    open_page = Mock(side_effect=error)
    pause = Mock()
    monkeypatch.setattr("app.fetcher.urlopen", open_page)
    monkeypatch.setattr("app.fetcher.sleep", pause)

    with pytest.raises(FetchError, match="HTTPS 连接提前断开，已尝试 3 次") as exc_info:
        PageFetcher(Settings.from_project_root(tmp_path)).fetch(URL)

    assert exc_info.value.__cause__ is error
    assert open_page.call_count == 3
    assert [call.args[0] for call in pause.call_args_list] == [0.25, 0.5]


def test_does_not_retry_certificate_errors(monkeypatch, tmp_path) -> None:
    open_page = Mock(side_effect=URLError(ssl.SSLCertVerificationError("certificate verification failed")))
    monkeypatch.setattr("app.fetcher.urlopen", open_page)

    with pytest.raises(FetchError, match="certificate verification failed"):
        PageFetcher(Settings.from_project_root(tmp_path)).fetch(URL)

    open_page.assert_called_once()
