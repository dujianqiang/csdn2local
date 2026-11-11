from __future__ import annotations

import io
from email.message import Message
from urllib.error import HTTPError

import pytest

from app.config import Settings
from app.fetcher import FetchError, PageFetcher


URL = "https://blog.csdn.net/sinat_27016095/article/details/148428154"


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


@pytest.mark.parametrize("marker", ["登录后查看", "请登录后阅读"])
def test_explicit_access_message_is_rejected(monkeypatch, tmp_path, marker: str) -> None:
    monkeypatch.setattr("app.fetcher.urlopen", lambda *_args, **_kwargs: FakeResponse(f"<p>{marker}</p>".encode()))

    with pytest.raises(FetchError, match="登录或付费"):
        PageFetcher(Settings.from_project_root(tmp_path)).fetch(URL)


def test_http_error_is_reported(monkeypatch, tmp_path) -> None:
    error = HTTPError(URL, 521, "Origin unavailable", Message(), io.BytesIO())
    monkeypatch.setattr("app.fetcher.urlopen", lambda *_args, **_kwargs: (_ for _ in ()).throw(error))

    with pytest.raises(FetchError, match="HTTP 521"):
        PageFetcher(Settings.from_project_root(tmp_path)).fetch(URL)
