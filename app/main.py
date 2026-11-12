from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import asdict
import os
from pathlib import Path
import re
from time import monotonic
from urllib.parse import quote, urlencode

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from loguru import logger

from app.archive import ArchiveFailure, ArchiveService
from app.config import settings
from app.fetcher import FetchError
from app.topic import TopicService
from app.topic_history import list_topic_archives
from app.topic_jobs import TopicJobBusy, TopicJobs


templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
archive_service = ArchiveService(settings)
topic_service = TopicService(archive_service)
topic_jobs = TopicJobs()


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.ensure_directories()
    browser_cache = Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH", Path.home() / "AppData" / "Local" / "ms-playwright"))
    if not browser_cache.exists():
        logger.warning("PDF output is unavailable until Playwright Chromium is installed")
    yield


app = FastAPI(title="csdn 单个连接下载", version="0.1.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def home(
    request: Request,
    q: str = Query(default=""),
    url: str = Query(default=""),
    formats: list[str] = Query(default=["html"]),
) -> HTMLResponse:
    source_results = archive_service.index.search(q) if q.strip() else archive_service.index.list_all()
    results = [_with_file_url(item) for item in source_results]
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"query": q, "results": results, "url": url, "formats": formats},
    )


@app.get("/topic", response_class=HTMLResponse)
def topic_home(
    request: Request,
    topic_url: str = "",
    output_format: str = "html",
    concurrency: str = "1",
) -> HTMLResponse:
    return _render_topic_form(
        request, error=None, topic_url=topic_url, output_format=output_format, concurrency=concurrency
    )


def _render_topic_form(
    request: Request, *, status_code: int = 200, active_id: str | None = None, **context: object
) -> HTMLResponse:
    history = [
        (record, _file_url(record.output_path)) for record in list_topic_archives(settings.data_dir)
    ]
    active_id = active_id or topic_jobs.active_id
    return templates.TemplateResponse(
        request=request,
        name="topic.html",
        context={
            **context,
            "article_limit": settings.topic_article_limit,
            "history": history,
            "active_job_url": request.url_for("topic_progress", job_id=active_id) if active_id else None,
        },
        status_code=status_code,
    )


@app.post("/archive", response_class=HTMLResponse)
def archive_article(
    request: Request,
    url: str = Form(...),
    formats: list[str] = Form(default=[]),
) -> HTMLResponse:
    selected = formats or ["html"]
    edit_url = "/?" + urlencode({"url": url, "formats": selected}, doseq=True) + "#url"
    try:
        result = archive_service.archive(url, selected)
    except (FetchError, ArchiveFailure, ValueError) as exc:
        return templates.TemplateResponse(
            request=request,
            name="result.html",
            context={"success": False, "partial": False, "error": str(exc), "url": url, "formats": selected, "edit_url": edit_url},
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
            "edit_url": edit_url,
            "result": result,
            "links": links,
        },
    )


@app.post("/topic", response_class=HTMLResponse, response_model=None)
def download_topic(
    request: Request,
    topic_url: str = Form(...),
    output_format: str = Form(default="html"),
    concurrency: str = Form(default="1"),
    article_html: list[UploadFile] = File(default=[]),
) -> HTMLResponse | RedirectResponse:
    context = {
        "topic_url": topic_url,
        "output_format": output_format,
        "concurrency": concurrency,
    }
    try:
        selected_format = TopicService.normalize_output_format(output_format)
        worker_count = TopicService.normalize_concurrency(concurrency)
        saved_articles = _read_saved_articles(article_html)
        job_id = topic_jobs.submit(topic_service, topic_url, selected_format, worker_count, saved_articles)
    except ValueError as exc:
        return _render_topic_form(request, **context, error=str(exc), status_code=400)
    except TopicJobBusy as exc:
        return _render_topic_form(
            request,
            **context,
            error=str(exc),
            active_id=exc.job_id,
            status_code=409,
        )
    return RedirectResponse(request.url_for("topic_progress", job_id=job_id), status_code=303)


def _read_saved_articles(uploads: list[UploadFile]) -> dict[str, str]:
    articles: dict[str, str] = {}
    remaining = 32 * 1024 * 1024
    for upload in uploads:
        if not upload.filename:
            continue
        match = re.fullmatch(r"([0-9]+)\.html?", upload.filename, re.IGNORECASE)
        if not match:
            raise ValueError("请用文章 ID 给另存的文件命名，例如 148028338.html。")
        article_id = match.group(1)
        if article_id in articles:
            raise ValueError(f"同一文章只能选择一个 HTML 文件：{article_id}")
        content = upload.file.read(remaining + 1)
        remaining -= len(content)
        if remaining < 0:
            raise ValueError("一次上传的 HTML 文件合计不能超过 32 MB。")
        try:
            articles[article_id] = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError(f"{upload.filename} 不是 UTF-8 编码的 HTML 文件。") from exc
    return articles


@app.get("/topic/jobs/{job_id}", response_class=HTMLResponse)
def topic_progress(request: Request, job_id: str) -> HTMLResponse:
    job = topic_jobs.get(job_id)
    headers = {"Cache-Control": "no-store"}
    if job is None:
        return templates.TemplateResponse(
            request=request,
            name="topic_result.html",
            context={"success": False, "error": "找不到此任务，请返回专题下载页面重新提交。"},
            status_code=404,
            headers=headers,
        )
    if job.result is None and job.error is None:
        return templates.TemplateResponse(
            request=request,
            name="topic_progress.html",
            context={
                "job": job,
                "elapsed": int(monotonic() - job.started_at),
                "status_url": request.url_for("topic_status", job_id=job_id),
                "job_url": request.url_for("topic_progress", job_id=job_id),
            },
            headers=headers,
        )

    result = job.result
    return templates.TemplateResponse(
        request=request,
        name="topic_result.html",
        context={
            "success": result is not None,
            "partial": result is not None and result.status == "partial",
            "result": result,
            "articles": result.articles if result else job.failed_articles,
            "error": job.error,
            "output_url": _file_url(result.output_path) if result else None,
            "topic_url": job.topic_url,
            "output_format": job.output_format,
            "concurrency": job.concurrency,
            "progress": job.progress,
            "edit_url": "/topic?" + urlencode({
                "topic_url": job.topic_url, "output_format": job.output_format, "concurrency": job.concurrency
            }) + "#topic-url",
        },
        headers=headers,
    )


@app.get("/topic/jobs/{job_id}/status")
def topic_status(job_id: str) -> JSONResponse:
    job = topic_jobs.get(job_id)
    headers = {"Cache-Control": "no-store"}
    if job is None:
        return JSONResponse({"finished": True}, status_code=404, headers=headers)
    return JSONResponse({
        **asdict(job.progress),
        "finished": job.result is not None or job.error is not None,
        "elapsed": int(monotonic() - job.started_at),
    }, headers=headers)


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
