from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from threading import Lock
from time import monotonic
from uuid import uuid4

from loguru import logger

from app.fetcher import FetchError
from app.outputs import OutputError
from app.topic import TopicArticle, TopicAttempt, TopicFailure, TopicProgress, TopicResult, TopicService


class TopicJobBusy(RuntimeError):
    def __init__(self, job_id: str):
        super().__init__("已有专题正在处理，请等它完成后再提交。")
        self.job_id = job_id


@dataclass(frozen=True)
class TopicJob:
    topic_url: str
    output_format: str
    concurrency: int
    article_limit: int
    retry_position: int | None = None
    batch_retry: bool = False
    started_at: float = field(default_factory=monotonic)
    progress: TopicProgress = field(default_factory=TopicProgress)
    result: TopicResult | None = None
    error: str | None = None
    failed_articles: tuple[TopicArticle, ...] = ()
    failed_attempt: TopicAttempt | None = None


class TopicJobs:
    def __init__(self) -> None:
        self._jobs: dict[str, TopicJob] = {}
        self._active_id: str | None = None
        self._lock = Lock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="topic-download")

    def submit(
        self, service: TopicService, topic_url: str, output_format: str, concurrency: int,
        article_limit: int, saved_articles: dict[str, str] | None = None,
    ) -> str:
        job = TopicJob(topic_url, output_format, concurrency, article_limit)
        return self._submit(job, lambda progress: service.download(
            topic_url, output_format, concurrency,
            article_limit=article_limit, on_progress=progress, saved_articles=saved_articles,
        ))

    def submit_retry(
        self, service: TopicService, attempt: TopicAttempt, position: int,
        *, refresh: Callable[[], TopicAttempt] | None = None, saved_html: str | None = None,
    ) -> str:
        job = TopicJob(
            attempt.topic_url, attempt.output_format, attempt.concurrency, attempt.article_limit,
            retry_position=position,
        )
        return self._submit(job, lambda progress: service.retry_article(
            refresh() if refresh else attempt, position, on_progress=progress, saved_html=saved_html
        ))

    def submit_batch_retry(
        self, service: TopicService, attempt: TopicAttempt, positions: set[int] | None,
        *, refresh: Callable[[], TopicAttempt] | None = None,
    ) -> str:
        job = TopicJob(attempt.topic_url, attempt.output_format, attempt.concurrency, attempt.article_limit,
                       batch_retry=True, progress=TopicProgress("downloading"))
        return self._submit(job, lambda progress: service.retry_articles(
            refresh() if refresh else attempt, positions, on_progress=progress,
        ))

    def _submit(
        self, job: TopicJob, operation: Callable[[Callable[[TopicProgress], None]], TopicResult]
    ) -> str:
        with self._lock:
            if self._active_id is not None:
                raise TopicJobBusy(self._active_id)
            job_id = uuid4().hex
            self._executor.submit(self._run, job_id, operation)
            self._jobs[job_id] = job
            self._active_id = job_id
            if len(self._jobs) > 20:
                del self._jobs[next(iter(self._jobs))]
        return job_id

    def get(self, job_id: str) -> TopicJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    @property
    def active_id(self) -> str | None:
        with self._lock:
            return self._active_id

    def _run(
        self, job_id: str, operation: Callable[[Callable[[TopicProgress], None]], TopicResult]
    ) -> None:
        def record_progress(progress: TopicProgress) -> None:
            with self._lock:
                self._jobs[job_id] = replace(self._jobs[job_id], progress=progress)

        result = None
        error = None
        failed_articles: tuple[TopicArticle, ...] = ()
        failed_attempt = None
        try:
            downloaded = operation(record_progress)
            # The result page needs article summaries, not copies of every article body.
            result = replace(
                downloaded,
                articles=[replace(article, body_html="", work_assets=None) for article in downloaded.articles],
            )
        except TopicFailure as exc:
            error = str(exc)
            failed_articles = tuple(exc.articles)
            failed_attempt = exc.attempt
        except (FetchError, OutputError, ValueError) as exc:
            error = str(exc) or "专题下载失败，请重新下载。"
        except Exception:
            logger.exception("专题任务执行失败")
            error = "保存专题时发生错误，请重新下载。"

        with self._lock:
            self._jobs[job_id] = replace(
                self._jobs[job_id], result=result, error=error,
                failed_articles=failed_articles, failed_attempt=failed_attempt,
            )
            self._active_id = None
