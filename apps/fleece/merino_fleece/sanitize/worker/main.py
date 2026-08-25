"""Entrypoint for the search term sanitization queue consumer.

Runs as its own process consuming the Pub/Sub backup channel Merino falls back to when direct
submission to merino-fleece fails. It brings up the same sanitization dependencies the app
lifespan does, so both paths classify and log search terms identically.
"""

import asyncio
import logging
import signal

from gcloud.aio.pubsub import SubscriberClient, subscribe
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
from merino_fleece.sanitize.worker.worker import SubscriberTuning, build_handler, heartbeat

# Named explicitly rather than via `__name__`: this module is executed as a script
# (`uv run python .../sanitize/worker/main.py`), so `__name__` is "__main__" -- a logger
# outside the `merino_fleece` tree, which `configure_logging`'s `dictConfig` disables
# along with every other unconfigured logger. Every record from this module would be dropped.
logger = logging.getLogger("merino_fleece.sanitize.worker.main")


async def main() -> None:
    """Bring up the sanitization dependencies, then consume messages until stopped.

    Mirrors the FastAPI app's lifespan, including its teardown order: the exempts and the
    NER thread pool outlive the subscriber, because cancelling it drains the messages
    already in flight -- and those still consult both.

    `subscribe()` runs until cancelled, or raises if one of its internal workers dies. That
    exception is left to propagate so the process exits non-zero and Kubernetes restarts
    the pod, rather than idling in a half-broken state.
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

    tuning = SubscriberTuning.derive(
        ack_deadline_s=settings.pubsub.ack_deadline_sec,
        ner_workers=settings.pii.executor_max_workers,
    )

    tasks: list[asyncio.Task] = []
    try:
        async with SubscriberClient() as client:
            subscriber = asyncio.create_task(
                subscribe(
                    settings.pubsub.subscription,
                    build_handler(tuning.sanitize_timeout_s),
                    client,
                    # Pinned to one; `SubscriberTuning` is only valid for a single
                    # producer, since each one gets its own queue and consumer.
                    num_producers=1,
                    max_messages_per_producer=tuning.max_messages_per_pull,
                    num_tasks_per_consumer=tuning.concurrency,
                    ack_deadline=settings.pubsub.ack_deadline_sec,
                )
            )
            tasks.append(subscriber)

            if settings.pubsub.heartbeat_path:
                tasks.append(
                    asyncio.create_task(
                        heartbeat(
                            settings.pubsub.heartbeat_path,
                            settings.pubsub.heartbeat_interval,
                        )
                    )
                )

            loop = asyncio.get_running_loop()
            for sig in (signal.SIGTERM, signal.SIGINT):
                # Handled on the loop rather than by interrupting an arbitrary frame.
                loop.add_signal_handler(sig, _handle_exit, subscriber, sig)

            logger.info(
                "Listening for messages",
                extra={
                    "subscription_name": settings.pubsub.subscription,
                    "concurrency": tuning.concurrency,
                    "max_messages_per_pull": tuning.max_messages_per_pull,
                    "sanitize_timeout_s": tuning.sanitize_timeout_s,
                },
            )
            try:
                await subscriber
            except asyncio.CancelledError:
                # Cancelled by the shutdown signal; `subscribe()` has drained by now.
                logger.info("Subscriber stopped")
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await exempts.shutdown()
        shutdown_executor()
        shutdown_detector()


def _handle_exit(subscriber: asyncio.Task, signum: signal.Signals) -> None:
    """Cancel the subscriber on SIGTERM/SIGINT so it drains in-flight messages."""
    logger.info("Received shutdown signal. Stopping queue subscriber...", extra={"signal": signum})
    subscriber.cancel()


if __name__ == "__main__":
    asyncio.run(main())
