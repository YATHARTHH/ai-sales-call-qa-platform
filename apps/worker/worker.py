"""Background worker daemon process."""

import asyncio
import json
import os
import signal

import redis.asyncio as aioredis

from apps.worker.tasks import (
    execute_smoke_job,
    execute_transcription_job,
    recover_stale_jobs,
)
from packages.infrastructure.config.settings import settings
from packages.observability.logging import configure_logging, get_logger

logger = get_logger("worker")


class SalesCallWorker:
    """Async worker polling Redis and executing background tasks."""

    def __init__(self) -> None:
        self.worker_id = f"worker-{os.getpid()}"
        self.running = True

    async def run(self) -> None:
        configure_logging(log_level=settings.log_level, json_format=(settings.log_format == "json"))
        logger.info("worker_started", worker_id=self.worker_id, redis=settings.redis_url)

        redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)

        recovery_counter = 0
        while self.running:
            try:
                # 1. Periodically run stale-job recovery every 10 cycles (~10s)
                recovery_counter += 1
                if recovery_counter >= 10:
                    recovery_counter = 0
                    try:
                        recovered = await recover_stale_jobs()
                        if recovered > 0:
                            logger.info("stale_jobs_recovered", count=recovered)
                    except Exception as e:
                        logger.warning("stale_job_recovery_error", error=str(e))

                # 2. Pop job from Redis list queue (timeout 1 second)
                item = await redis_client.blpop(
                    ["queue:smoke_job", "queue:ingest_job", "queue:transcription"], timeout=1
                )
                if item:
                    queue_name, data = item
                    payload = json.loads(data)
                    job_id = payload.get("job_id")
                    correlation_id = payload.get("correlation_id", "none")

                    if queue_name == "queue:smoke_job":
                        await execute_smoke_job(
                            job_id=job_id,
                            worker_id=self.worker_id,
                            correlation_id=correlation_id,
                        )
                    elif queue_name == "queue:transcription":
                        await execute_transcription_job(
                            job_id=job_id,
                            worker_id=self.worker_id,
                            correlation_id=correlation_id,
                        )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("worker_loop_error", error=str(e), exc_info=True)
                await asyncio.sleep(1)

        await redis_client.aclose()
        logger.info("worker_stopped", worker_id=self.worker_id)

    def stop(self) -> None:
        self.running = False


async def main():
    worker = SalesCallWorker()

    def _signal_handler():
        worker.stop()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            pass  # Windows does not support loop signal handlers

    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
