"""Entrypoint for the search term sanitization queue consumer.

Runs as its own process consuming the Pub/Sub backup channel Merino falls back
to when direct submission to merino-fleece fails. It brings up the same
sanitization dependencies as the fleece app lifespan does, so both paths
classify and log search terms identically.
"""

import asyncio
import logging
import signal

from merino_common.app_configs.config_logging import configure_logging
from merino_common.app_configs.config_sentry import configure_sentry

from merino_fleece.configs import settings
from merino_fleece.pii import (
    init_detector,
    init_executor,
    shutdown_detector,
    shutdown_executor,
)
from merino_fleece.sanitize import exempts
from merino_fleece.sanitize.worker.worker import FleeceQueueWorker

logger = logging.getLogger(__name__)


async def main() -> None:
    """Bring up the sanitization dependencies, then consume messages until stopped.

    Mirrors the FastAPI app's lifespan, including its teardown order: the exempts and the
    NER thread pool outlive the streaming pull, because the pull is opened with
    ``await_callbacks_on_shutdown=True`` and so drains in-flight batches -- which still
    consult both -- before ``start()`` returns.
    """
    configure_logging(
        log_format=settings.logging.format,
        level=settings.logging.level,
        can_propagate=settings.logging.can_propagate,
        current_env=settings.current_env,
        logger_name="merino_fleece",
    )
    configure_sentry(
        mode=settings.sentry.mode,
        dsn=settings.sentry.dsn,
        env=settings.sentry.env,
        traces_sample_rate=settings.sentry.traces_sample_rate,
    )
    init_detector()
    init_executor()
    await exempts.initialize()

    loop = asyncio.get_running_loop()
    worker = FleeceQueueWorker(
        subscription_name=settings.pubsub.subscription,
        loop=loop,
        sanitize_timeout_s=settings.pubsub.sanitize_timeout_sec,
        # Leasing is bounded by NER capacity, not by Pub/Sub's callback pool, so the
        # flow-control cap is derived from the thread pool this process actually has.
        max_messages=(settings.pubsub.messages_per_ner_worker * settings.pii.executor_max_workers),
        restart_stream=settings.pubsub.restart_stream,
        restart_backoff=settings.pubsub.restart_backoff,
        # Normalize to None if path is empty (disabled)
        heartbeat_path=settings.pubsub.heartbeat_path or None,
        heartbeat_interval=settings.pubsub.heartbeat_interval,
    )
    for sig in (signal.SIGTERM, signal.SIGINT):
        # Handled on the loop rather than by interrupting whichever thread is active.
        loop.add_signal_handler(sig, _handle_exit, worker, sig)

    try:
        # The streaming pull is blocking and synchronous, so it gets a thread of its own;
        # this keeps the loop free to run the sanitization callbacks.
        await asyncio.to_thread(worker.start)
    finally:
        await exempts.shutdown()
        shutdown_executor()
        shutdown_detector()


def _handle_exit(worker: FleeceQueueWorker, signum: signal.Signals) -> None:
    """Stop the streaming pull on SIGTERM/SIGINT, draining in-flight callbacks."""
    logger.info("Received shutdown signal. Stopping queue subscriber...", extra={"signal": signum})
    worker.stop()


if __name__ == "__main__":
    asyncio.run(main())
