from __future__ import annotations

from contextlib import asynccontextmanager
import os
from pathlib import Path
from urllib.parse import quote

import uvicorn
from fastapi import FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from loguru import logger

from app.archive import ArchiveFailure, ArchiveService
from app.config import settings
from app.fetcher import FetchError
from app.topic import TopicFailure, TopicService


templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
archive_service = ArchiveService(settings)
topic_service = TopicService(settings)


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.ensure_directories()
    browser_cache = Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH", Path.home() / "AppData" / "Local" / "ms-playwright"))
    if not browser_cache.exists():
        logger.warning("PDF output is unavailable until Playwright Chromium is installed")
    yield


app = FastAPI(title="csdn 单个连接下载", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def home(request: Request, q: str = Query(default="")) -> HTMLResponse:
    source_results = archive_service.index.search(q) if q.strip() else archive_service.index.list_all()
    results = [_with_file_url(item) for item in source_results]
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"query": q, "results": results, "error": None},
    )


@app.get("/topic", response_class=HTMLResponse)
def topic_home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="topic.html",
        context={"error": None, "topic_url": "", "output_format": "html", "concurrency": 1},
    )


@app.post("/archive", response_class=HTMLResponse)
def archive_article(
    request: Request,
    url: str = Form(...),
    formats: list[str] = Form(default=[]),
) -> HTMLResponse:
    selected = formats or ["html"]
    try:
        result = archive_service.archive(url, selected)
    except (FetchError, ArchiveFailure, ValueError) as exc:
        return templates.TemplateResponse(
            request=request,
            name="result.html",
            context={"success": False, "partial": False, "error": str(exc), "url": url, "formats": selected},
            status_code=400,
        )
    links = []
    for name in result.metadata.formats:
        path = getattr(result.paths, name)
        links.append({"name": name.upper(), "url": _file_url(path)})
    return templates.TemplateResponse(
        request=request,
        name="result.html",
        context={
            "success": True,
            "partial": result.status == "partial",
            "error": None,
            "url": url,
            "formats": selected,
            "result": result,
            "links": links,
        },
    )


@app.post("/topic", response_class=HTMLResponse)
def download_topic(
    request: Request,
    topic_url: str = Form(...),
    output_format: str = Form(default="html"),
    concurrency: str = Form(default="1"),
) -> HTMLResponse:
    try:
        result = topic_service.download(topic_url, output_format, concurrency)
    except (FetchError, TopicFailure, ValueError) as exc:
        return templates.TemplateResponse(
            request=request,
            name="topic_result.html",
            context={
                "success": False,
                "error": str(exc),
                "topic_url": topic_url,
                "output_format": output_format,
                "concurrency": concurrency,
            },
            status_code=400,
        )
    return templates.TemplateResponse(
        request=request,
        name="topic_result.html",
        context={
            "success": True,
            "partial": result.status == "partial",
            "result": result,
            "output_url": _file_url(result.output_path),
            "topic_url": topic_url,
            "output_format": output_format,
            "concurrency": concurrency,
        },
    )


@app.get("/files/{domain}/{article_dir}/{file_path:path}")
def serve_file(domain: str, article_dir: str, file_path: str) -> FileResponse:
    root = settings.data_dir.resolve()
    candidate = (root / domain / article_dir / file_path).resolve()
    if root not in candidate.parents or candidate.name == "index.sqlite3" or ".staging" in candidate.parts:
        raise HTTPException(status_code=404, detail="文件不存在")
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(candidate)


def _file_url(path: Path) -> str:
    relative = path.resolve().relative_to(settings.data_dir.resolve())
    return "/files/" + "/".join(quote(part, safe="") for part in relative.parts)


def _with_file_url(item: dict[str, object]) -> dict[str, object]:
    copied = dict(item)
    address = copied.get("address")
    copied["address"] = _file_url(Path(str(address))) if address else None
    return copied


def run() -> None:
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=False)


if __name__ == "__main__":
    run()
