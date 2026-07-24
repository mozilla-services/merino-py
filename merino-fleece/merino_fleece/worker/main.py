"""Entrypoint for queue consumer worker"""

import signal
import logging

from merino_fleece.worker.worker import FleeceQueueWorker
from merino_fleece.configs import settings

subscription = settings.pubsub.subscription
restart_stream = settings.pubsub.restart_stream

logger = logging.getLogger(__name__)

if __name__ == "__main__":
    worker = FleeceQueueWorker(subscription_name=subscription, restart_stream=restart_stream)

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
