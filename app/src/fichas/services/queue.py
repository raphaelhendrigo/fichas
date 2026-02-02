from __future__ import annotations

from redis import Redis
from rq import Queue

from fichas.settings import settings


def get_queue() -> Queue:
    return Queue("ocr", connection=Redis.from_url(settings.REDIS_URL))


def enqueue_process_ocr(job_id: str):
    from fichas.workers.ocr_worker import process_ocr_job

    queue = get_queue()
    timeout = max(600, int(settings.OCR_TIMEOUT_SECONDS) + 120)
    return queue.enqueue(process_ocr_job, job_id, job_timeout=timeout)
