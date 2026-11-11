from __future__ import annotations

import httpx
import pytest
import respx

from app.config import Settings
from app.fetcher import FetchError, PageFetcher


URL = "https://blog.csdn.net/sinat_27016095/article/details/148428154"


@respx.mock
def test_hidden_generic_recharge_component_does_not_reject_public_page(tmp_path) -> None:
    respx.get(URL).mock(
        return_value=httpx.Response(
            200,
            text="<div class='pay-code-content'>付费专栏</div><div id='content_views'>公开正文</div>",
        )
    )

    snapshot = PageFetcher(Settings.from_project_root(tmp_path)).fetch(URL)

    assert "公开正文" in snapshot.html


@respx.mock
@pytest.mark.parametrize("marker", ["登录后查看", "请登录后阅读"])
def test_explicit_access_message_is_rejected(tmp_path, marker: str) -> None:
    respx.get(URL).mock(return_value=httpx.Response(200, text=f"<p>{marker}</p>"))

    with pytest.raises(FetchError, match="登录或付费"):
        PageFetcher(Settings.from_project_root(tmp_path)).fetch(URL)
