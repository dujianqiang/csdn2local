from __future__ import annotations

import respx
from httpx import Response

from app.config import Settings
from app.resources import ResourceDownloader


@respx.mock
def test_resource_downloader_rewrites_local_assets_and_reports_failures(tmp_path) -> None:
    image_url = "https://blog.csdn.net/images/a.png"
    missing_url = "https://blog.csdn.net/images/missing.png"
    respx.get(image_url).mock(return_value=Response(200, content=b"png", headers={"content-type": "image/png"}))
    respx.get(missing_url).mock(return_value=Response(404))
    body = f'<p><img src="{image_url}"><img src="{missing_url}"></p>'

    result = ResourceDownloader(Settings.from_project_root(tmp_path)).download(
        body, "https://blog.csdn.net/demo/article/details/1", tmp_path / "assets"
    )

    assert "assets/a-" in result.body_html
    assert "data-csdn2local-missing=\"true\"" in result.body_html
    assert len(result.warnings) == 1
    assert list((tmp_path / "assets").iterdir())
