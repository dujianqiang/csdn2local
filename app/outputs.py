from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from threading import Lock

from playwright.sync_api import Browser, BrowserType, Error as PlaywrightError, sync_playwright

from app.parser import CODE_PRINT_CSS, render_article_document


_CHROMIUM_LAUNCH_LOCK = Lock()


class OutputError(RuntimeError):
    """An archive output could not be generated."""


def write_html(path: Path, title: str, body_html: str, *, source_url: str = "") -> None:
    path.write_text(render_article_document(title, body_html, source_url=source_url), encoding="utf-8")


def _launch_chromium(chromium: BrowserType) -> Browser:
    with _CHROMIUM_LAUNCH_LOCK:
        try:
            return chromium.launch(headless=True)
        except PlaywrightError as exc:
            if "Executable doesn't exist at " not in str(exc):
                raise
        try:
            subprocess.run(
                [sys.executable, "-m", "playwright", "install", "--only-shell", "chromium"],
                check=True,
                timeout=600,
            )
        except subprocess.TimeoutExpired as exc:
            raise OutputError("Chromium 下载超时。请检查网络连接后重试。") from exc
        except (OSError, subprocess.CalledProcessError) as exc:
            raise OutputError("Chromium 下载失败。请查看服务终端的安装日志，处理后重试。") from exc
        return chromium.launch(headless=True)


def write_pdf(html_path: Path, pdf_path: Path) -> None:
    try:
        with sync_playwright() as playwright:
            browser = _launch_chromium(playwright.chromium)
            try:
                page = browser.new_page()
                page.goto(html_path.as_uri(), wait_until="load")
                page.locator("details.code-block").evaluate_all("blocks => blocks.forEach(block => { block.open = true; })")
                page.add_style_tag(content=CODE_PRINT_CSS)
                page.pdf(
                    path=str(pdf_path),
                    format="A4",
                    print_background=True,
                    margin={"top": "18mm", "right": "14mm", "bottom": "18mm", "left": "14mm"},
                )
            finally:
                browser.close()
    except OutputError:
        raise
    except PlaywrightError as exc:
        if sys.platform == "linux" and "Host system is missing dependencies" in str(exc):
            raise OutputError(
                "Linux 缺少 Chromium 所需的系统库。请在项目虚拟环境中运行 "
                "python -m playwright install-deps chromium，然后重试。"
            ) from exc
        raise OutputError(f"PDF 生成失败：{exc}") from exc
    except Exception as exc:
        raise OutputError(f"PDF 生成失败：{exc}") from exc
