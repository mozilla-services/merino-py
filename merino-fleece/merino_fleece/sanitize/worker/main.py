"""Entrypoint for queue consumer worker"""

import signal
import logging

from merino_fleece.sanitize.worker.worker import FleeceQueueWorker
from merino_fleece.configs import settings

subscription = settings.pubsub.subscription
restart_stream = settings.pubsub.restart_stream
restart_backoff = settings.pubsub.restart_backoff
# Normalize to None if path is empty (disabled)
heartbeat_path = settings.pubsub.heartbeat_path or None
heartbeat_interval = settings.pubsub.heartbeat_interval

logger = logging.getLogger(__name__)

if __name__ == "__main__":
    worker = FleeceQueueWorker(
        subscription_name=subscription,
        restart_stream=restart_stream,
        restart_backoff=restart_backoff,
        heartbeat_path=heartbeat_path,
        heartbeat_interval=heartbeat_interval,
    )

    def handle_exit(signum, frame):
        """Shutdown signal handler (SIGTERM + SIGINT)"""
        logging.info(
            "Received shutdown signal. Stopping queue subscriber...", extra={"signal": signum}
        )
        worker.stop()

    # Register shutdown signals
    signal.signal(signal.SIGTERM, handle_exit)
    signal.signal(signal.SIGINT, handle_exit)

    worker.start()
