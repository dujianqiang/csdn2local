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


templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
archive_service = ArchiveService(settings)


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.ensure_directories()
    browser_cache = Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH", Path.home() / "AppData" / "Local" / "ms-playwright"))
    if not browser_cache.exists():
        logger.warning("PDF output is unavailable until Playwright Chromium is installed")
    yield


app = FastAPI(title="csdn2local", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def home(request: Request, q: str = Query(default="")) -> HTMLResponse:
    results = [_with_file_url(item) for item in archive_service.index.search(q)] if q.strip() else []
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"query": q, "results": results, "error": None},
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
