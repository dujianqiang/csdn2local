from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import asdict
from functools import partial
import os
from pathlib import Path
import re
from tempfile import SpooledTemporaryFile
from time import monotonic
from urllib.parse import quote, urlencode

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from loguru import logger
from starlette.background import BackgroundTask

from app.archive import ArchiveFailure, ArchiveService
from app.config import settings
from app.fetcher import FetchError
from app.markdown import write_markdown_bundle
from app.parser import render_article_document
from app.storage import alias_target
from app.topic import TopicAttempt, TopicProgress, TopicService
from app.topic_history import TopicArchive, group_topic_archives, list_topic_archives, read_topic_archive
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
    history_format: str = "",
) -> HTMLResponse:
    history_format = history_format if history_format in ArchiveService.OUTPUT_FORMATS else ""
    source_results = archive_service.index.search(q) if q.strip() else archive_service.index.list_all()
    results = []
    for item in source_results:
        outputs = item.get("outputs", {})
        address = item["address"]
        if history_format:
            if history_format not in outputs:
                continue
            address = outputs[history_format]
            outputs = {history_format: address}
        results.append({
            **item,
            "address": _download_url(Path(address)),
            "outputs": {name: _download_url(Path(path)) for name, path in outputs.items()},
        })
    selected = next((name for name in formats if name in ArchiveService.OUTPUT_FORMATS), "html")
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "query": q, "results": results, "url": url, "selected_format": selected,
            "output_formats": ArchiveService.OUTPUT_FORMATS,
            "history_format": history_format,
        },
    )


@app.get("/topic", response_class=HTMLResponse)
def topic_home(
    request: Request,
    topic_url: str = "",
    output_format: str = "html",
    concurrency: str = "1",
    article_limit: str | None = None,
    history_format: str = "",
) -> HTMLResponse:
    return _render_topic_form(
        request, error=None, topic_url=topic_url, output_format=output_format, concurrency=concurrency,
        article_limit=settings.topic_article_limit if article_limit is None else article_limit,
        history_format=history_format,
    )


def _render_topic_form(
    request: Request, *, status_code: int = 200, active_id: str | None = None,
    history_format: str = "", **context: object,
) -> HTMLResponse:
    history_format = history_format if history_format in TopicService.OUTPUT_FORMATS else ""
    history = [
        [(record, _topic_detail_url(record.attempt)) for record in group]
        for group in group_topic_archives(settings.data_dir, output_format=history_format)
    ]
    active_id = active_id or topic_jobs.active_id
    return templates.TemplateResponse(
        request=request,
        name="topic.html",
        context={
            **context,
            "history": history,
            "history_format": history_format,
            "output_formats": TopicService.OUTPUT_FORMATS,
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
    selected = formats[0].strip().lower() if formats else "html"
    edit_url = "/?" + urlencode({"url": url, "formats": selected}) + "#url"
    try:
        if len(formats) > 1 or selected not in ArchiveService.OUTPUT_FORMATS:
            raise ValueError("保存格式只能选择 HTML、PDF 或 Markdown 其中一种。")
        result = archive_service.archive(url, [selected])
    except (FetchError, ArchiveFailure, ValueError) as exc:
        return templates.TemplateResponse(
            request=request,
            name="result.html",
            context={
                "success": False, "error": str(exc), "url": url,
                "selected_format": selected if selected in ArchiveService.OUTPUT_FORMATS else "html",
                "edit_url": edit_url,
            },
            status_code=400,
        )
    return templates.TemplateResponse(
        request=request,
        name="result.html",
        context={
            "success": True,
            "partial": result.status == "partial",
            "selected_format": selected,
            "result": result,
            "output_url": _download_url(getattr(result.paths, selected)),
        },
    )


@app.post("/topic", response_class=HTMLResponse, response_model=None)
def download_topic(
    request: Request,
    topic_url: str = Form(...),
    output_format: list[str] = Form(default=["html"]),
    concurrency: str = Form(default="1"),
    article_limit: str | None = Form(default=None),
    article_html: list[UploadFile] = File(default=[]),
) -> HTMLResponse | RedirectResponse:
    context = {
        "topic_url": topic_url,
        "output_format": output_format[0],
        "concurrency": concurrency,
        "article_limit": settings.topic_article_limit if article_limit is None else article_limit,
    }
    try:
        if len(output_format) != 1:
            raise ValueError("专题输出格式只能选择 HTML、EPUB、PDF 或 Markdown 其中一种")
        selected_format = TopicService.normalize_output_format(output_format[0])
        worker_count = TopicService.normalize_concurrency(concurrency)
        limit = TopicService.normalize_article_limit(context["article_limit"])
        saved_articles = _read_saved_articles(article_html)
        job_id = topic_jobs.submit(topic_service, topic_url, selected_format, worker_count, limit, saved_articles)
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
    record = read_topic_archive(result.metadata_path.parent) if result else None
    if job.failed_attempt and any(not article.error for article in job.failed_attempt.articles):
        record = read_topic_archive(job.failed_attempt.target.archive_dir)
        if record:
            result = record.attempt.as_result()
    return templates.TemplateResponse(
        request=request,
        name="topic_result.html",
        context={
            "success": result is not None,
            "partial": result is not None and result.status == "partial",
            "result": result,
            "articles": result.articles if result else job.failed_articles,
            "error": job.error,
            "output_url": _download_url(result.output_path) if result else None,
            "topic_url": job.topic_url,
            "output_format": job.output_format,
            "concurrency": job.concurrency,
            "article_limit": job.article_limit,
            "progress": job.progress,
            "retry_base": f"/topic/jobs/{job_id}/retry" if job.failed_attempt or (record and record.can_retry) else None,
            "edit_url": _topic_edit_url(job.topic_url, job.output_format, job.concurrency, job.article_limit),
        },
        headers=headers,
    )


@app.get("/topic/history/{archive_ref:path}", response_class=HTMLResponse)
def topic_history(request: Request, archive_ref: str) -> HTMLResponse:
    record = _history_record(archive_ref)
    attempt = record.attempt
    result = attempt.as_result()
    versions = [
        (item, _topic_detail_url(item.attempt))
        for item in list_topic_archives(settings.data_dir)
        if item.identity == record.identity
    ]
    total = len(attempt.articles)
    return templates.TemplateResponse(
        request=request,
        name="topic_result.html",
        context={
            "success": True,
            "partial": result.status == "partial",
            "archived": True,
            "versions": versions,
            "result": result,
            "articles": result.articles,
            "output_url": _download_url(result.output_path),
            "topic_url": attempt.topic_url,
            "output_format": attempt.output_format,
            "concurrency": attempt.concurrency,
            "article_limit": attempt.article_limit,
            "progress": TopicProgress(total=total, discovered_total=attempt.discovered_total),
            "retry_base": _topic_detail_url(attempt) + "/retry" if record.can_retry else None,
            "edit_url": _topic_edit_url(
                attempt.topic_url, attempt.output_format, attempt.concurrency, attempt.article_limit
            ) if attempt.topic_url else None,
        },
        headers={"Cache-Control": "no-store"},
    )


@app.post("/topic/history/{archive_ref:path}/retry/{position}")
def retry_archived_topic_article(
    request: Request, archive_ref: str, position: int, article_html: UploadFile | None = File(default=None)
) -> RedirectResponse:
    record = _history_record(archive_ref)
    return _submit_article_retry(request, position, article_html, record=record)


@app.post("/topic/jobs/{job_id}/retry/{position}")
def retry_topic_article(
    request: Request, job_id: str, position: int, article_html: UploadFile | None = File(default=None)
) -> RedirectResponse:
    job = topic_jobs.get(job_id)
    if job and job.failed_attempt:
        if any(not article.error for article in job.failed_attempt.articles):
            record = read_topic_archive(job.failed_attempt.target.archive_dir)
            if record:
                return _submit_article_retry(request, position, article_html, record=record)
            raise HTTPException(status_code=404, detail="找不到可重试的原归档。")
        return _submit_article_retry(request, position, article_html, failed_attempt=job.failed_attempt)
    if job and job.result:
        record = read_topic_archive(job.result.metadata_path.parent)
        if record:
            return _submit_article_retry(request, position, article_html, record=record)
    raise HTTPException(status_code=404, detail="找不到可重试的专题任务。")


def _submit_article_retry(
    request: Request, position: int, article_html: UploadFile | None, *, record: TopicArchive | None = None,
    failed_attempt: TopicAttempt | None = None,
) -> RedirectResponse:
    attempt = record.attempt if record else failed_attempt
    if not attempt or (record and not record.can_retry):
        raise HTTPException(status_code=409, detail="这个归档无法逐篇重试，请重新下载专题。")
    article = next((item for item in attempt.articles if item.position == position and item.error), None)
    if article is None:
        raise HTTPException(status_code=404, detail="这篇文章当前无需重试。")
    saved_html = None
    if article_html is not None:
        try:
            articles = _read_saved_articles([article_html])
            article_id = article.article_id
            if article_id not in articles:
                raise ValueError(f"请选择这篇文章另存的 {article_id}.html 文件。")
            saved_html = articles[article_id]
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def refresh() -> TopicAttempt:
        latest = read_topic_archive(attempt.target.archive_dir)
        if latest is None or not latest.can_retry:
            raise ValueError("找不到可重试的原归档。")
        return latest.attempt

    try:
        job_id = topic_jobs.submit_retry(
            topic_service, attempt, position, refresh=refresh if record else None, saved_html=saved_html
        )
    except TopicJobBusy as exc:
        job_id = exc.job_id
    return RedirectResponse(request.url_for("topic_progress", job_id=job_id), status_code=303)


def _history_record(archive_ref: str) -> TopicArchive:
    parts = archive_ref.split("/")
    for part in parts:
        if not part or part.startswith(".") or any(char in part for char in "\\:\x00"):
            raise HTTPException(status_code=404, detail="找不到专题归档。")
    root = settings.data_dir.resolve()
    if len(parts) == 4 and parts[0] == "topics":
        record = read_topic_archive(root.joinpath(*parts))
    elif len(parts) == 2:
        legacy = Path(parts[0], "topics", parts[1])
        target = alias_target(root, legacy)
        record = read_topic_archive(target) if target else None
        if record is None:
            record = read_topic_archive(root / legacy)
    else:
        raise HTTPException(status_code=404, detail="找不到专题归档。")
    if not record:
        raise HTTPException(status_code=404, detail="找不到专题归档。")
    return record


def _topic_detail_url(attempt: TopicAttempt) -> str:
    parts = attempt.target.archive_dir.relative_to(settings.data_dir.resolve()).parts
    if len(parts) == 3 and parts[1] == "topics":
        parts = (parts[0], parts[2])
    return "/topic/history/" + "/".join(quote(part, safe="") for part in parts)


def _topic_edit_url(topic_url: str, output_format: str, concurrency: int, article_limit: int) -> str:
    return "/topic?" + urlencode({
        "topic_url": topic_url, "output_format": output_format,
        "concurrency": concurrency, "article_limit": article_limit,
    }) + "#topic-url"


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
def serve_file(domain: str, article_dir: str, file_path: str, bundle: bool = False, article: int | None = None) -> Response:
    root = settings.data_dir.resolve()
    parts = (domain, article_dir, *file_path.split("/"))
    if any(not part or part.startswith(".") or any(char in part for char in "\\:\x00") for part in parts):
        raise HTTPException(status_code=404, detail="文件不存在")
    candidate = root.joinpath(*parts).resolve()
    if not candidate.is_file() and domain not in {"articles", "topics"}:
        archive_depth = 3 if article_dir == "topics" else 2
        target = alias_target(root, Path(*parts[:archive_depth]))
        if target:
            candidate = target.joinpath(*parts[archive_depth:]).resolve()
    if root not in candidate.parents or candidate.name.casefold() in {"index.sqlite3", TopicService.BODY_CACHE}:
        raise HTTPException(status_code=404, detail="文件不存在")
    if any(part.startswith(".") for part in candidate.relative_to(root).parts):
        raise HTTPException(status_code=404, detail="文件不存在")
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    if article is not None and candidate.name in {"topic.epub", "topic.md"}:
        return _read_topic_article(candidate, article)
    if candidate.name in {"article.md", "topic.md"}:
        if bundle:
            archive = SpooledTemporaryFile(max_size=8 * 1024 * 1024)
            try:
                write_markdown_bundle(candidate, archive)
                size = archive.tell()
                archive.seek(0)
            except BaseException:
                archive.close()
                raise
            return StreamingResponse(
                iter(partial(archive.read, 64 * 1024), b""),
                media_type="application/zip",
                headers={
                    "Content-Disposition": f'attachment; filename="{candidate.stem}.zip"',
                    "Content-Length": str(size),
                },
                background=BackgroundTask(archive.close),
            )
        return FileResponse(candidate, media_type="text/markdown", filename=candidate.name)
    return FileResponse(candidate)


def _read_topic_article(output: Path, position: int) -> HTMLResponse:
    record = read_topic_archive(output.parent)
    if record is None or record.attempt.output_path != output:
        raise HTTPException(status_code=404, detail="找不到专题归档。")
    article = next((item for item in record.attempt.articles if item.position == position and not item.error), None)
    if article is None:
        raise HTTPException(status_code=404, detail="找不到已归档的文章。")
    try:
        body = TopicService.archived_bodies(record.attempt).get(str(position))
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="无法读取本地正文，请重新下载专题。") from exc
    if body is None:
        raise HTTPException(status_code=404, detail="归档缺少这篇文章的正文。")
    return HTMLResponse(
        render_article_document(article.title or f"文章 {position}", body, source_url=article.url),
        headers={"Content-Security-Policy": "default-src 'none'; img-src 'self' data:; media-src 'self'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"},
    )


def _file_url(path: Path) -> str:
    relative = path.resolve().relative_to(settings.data_dir.resolve())
    return "/files/" + "/".join(quote(part, safe="") for part in relative.parts)


def _download_url(path: Path) -> str:
    url = _file_url(path)
    return url + "?bundle=1" if path.suffix == ".md" else url


def run() -> None:
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=False)


if __name__ == "__main__":
    run()
