"""The module for service governance."""

import asyncio

import aiodogstatsd

from circuitbreaker import CircuitBreakerMonitor

from merino.utils import cron
from merino.configs import settings
from merino.utils.metrics import get_metrics_client


class Governing:
    """Merino service governing daemon."""

    cron_task: asyncio.Task | None
    metrics_client: aiodogstatsd.Client

    def __init__(self, metrics_client: aiodogstatsd.Client) -> None:
        self.metrics_client = metrics_client
        self.cron_task = None

    def start(self) -> None:
        """Start the governing deamon."""
        cron_job = cron.Job(
            name="service_governing_daemon",
            interval=settings.governance.cron_interval_sec,
            condition=lambda: True,
            task=self.cron,
        )
        self.cron_task = asyncio.create_task(cron_job())

    def shutdown(self) -> None:
        """Shutdown the governing daemon."""
        if self.cron_task is not None:
            _ = self.cron_task.cancel()
            self.cron_task = None

    def _emit_circuit_metrics(self) -> None:
        """Emit circuit breaker metrics."""
        for circuit in CircuitBreakerMonitor.get_circuits():
            self.metrics_client.gauge(
                f"governance.circuits.{circuit.name}",
                value=circuit.state,
                tags={"failure_count": circuit.failure_count},
            )

    async def cron(self) -> None:
        """Cronjob callback. Service governing background tasks can be done here."""
        self._emit_circuit_metrics()


# The governing daemon singleton. Use `start()` and `shutdown()` to interact with it.
governing: Governing = Governing(get_metrics_client())


def start() -> None:
    """Start the governing deamon. This should only be called once."""
    governing.start()


def shutdown() -> None:
    """Shutdown the governing daemon. This should only be called once."""
    governing.shutdown()
