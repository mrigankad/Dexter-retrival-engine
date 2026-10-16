"""
Ingestion worker.

``enqueue_ingestion`` pushes a job to Redis when a worker is available
(INGESTION_MODE=queue and Redis reachable); otherwise it processes the job in
the API process as a background task so uploads still work in dev/test.

Run the worker: ``python -m src.ingestion.worker``.
"""

from __future__ import annotations

import asyncio
import json
import signal
from typing import Optional, Set

from src.contracts import IngestionJob
from src.core.config import settings
from src.core.logger import get_logger, setup_logging
from src.infrastructure.cache import get_redis_client, redis_available

from .pipeline import get_ingestion_pipeline

logger = get_logger(__name__)

_background_tasks: Set[asyncio.Task] = set()


async def enqueue_ingestion(job: IngestionJob) -> str:
    """Return 'queued' or 'inline' depending on where the job will run."""
    if settings.ingestion_mode == "queue" and await redis_available():
        client = get_redis_client()
        await client.rpush(settings.redis_queue_name, job.model_dump_json())
        logger.info("Ingestion job queued", document_id=job.document_id)
        return "queued"
    task = asyncio.create_task(get_ingestion_pipeline().process(job))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    logger.info("Ingestion job running inline", document_id=job.document_id)
    return "inline"


async def wait_for_inline_jobs() -> None:
    """Tests / shutdown: wait for any inline ingestion tasks."""
    if _background_tasks:
        await asyncio.gather(*list(_background_tasks), return_exceptions=True)


class IngestionWorker:
    def __init__(self, queue_name: Optional[str] = None):
        self.queue_name = queue_name or settings.redis_queue_name
        self.pipeline = get_ingestion_pipeline()
        self.running = False

    async def process_raw(self, raw: str) -> bool:
        try:
            job = IngestionJob.model_validate(json.loads(raw))
        except Exception as exc:
            logger.error("Bad ingestion job payload", error=str(exc))
            return False
        result = await self.pipeline.process(job)
        return result.status == "completed"

    async def run(self) -> None:
        client = get_redis_client()
        if client is None:
            raise RuntimeError("Redis is disabled; worker cannot run. Set INGESTION_MODE=inline instead.")
        self.running = True
        logger.info("Ingestion worker started", queue=self.queue_name)
        while self.running:
            try:
                item = await client.brpop(self.queue_name, timeout=5)
                if item:
                    _, raw = item
                    await self.process_raw(raw)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception("Worker loop error", error=str(exc))
                await asyncio.sleep(1)
        logger.info("Ingestion worker stopped")

    def stop(self) -> None:
        self.running = False


async def main() -> None:
    setup_logging(log_level=settings.log_level, json_logs=settings.is_production)
    from src.infrastructure.database import init_db
    await init_db(seed_admin=False)
    worker = IngestionWorker()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, worker.stop)
        except NotImplementedError:
            pass
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
