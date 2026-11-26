"""Running hook-eye's checks in the background and reporting their liveness."""

import asyncio
import contextlib
import logging
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass

from merino_common.utils import cron

logger = logging.getLogger(__name__)

# A check that hasn't finished a run in this many intervals has stalled. Each check must bound
# its own run time below its interval, e.g. with a request timeout.
STALL_INTERVALS = 3


@dataclass(frozen=True)
class RunningCheck:
    """A check whose loop is running in the background."""

    name: str
    task: asyncio.Task[None]
    interval_sec: float
    seconds_since_last_attempt: Callable[[], float]

    def is_alive(self) -> bool:
        """Return whether the loop is running and finished a run, successful or not, recently.

        This checks the monitor, not its target: a failed run still counts, since restarting
        hook-eye wouldn't fix the target. Each check reports those through its own metrics.
        """
        stall_after = STALL_INTERVALS * self.interval_sec
        return not self.task.done() and self.seconds_since_last_attempt() <= stall_after


@asynccontextmanager
async def run_check(
    *,
    name: str,
    interval_sec: float,
    run: cron.Task,
    seconds_since_last_attempt: Callable[[], float],
    on_stop: Callable[[], None],
) -> AsyncGenerator[RunningCheck]:
    """Run `run` every `interval_sec` seconds until the context exits.

    Args:
        name: Identifies the check in logs.
        interval_sec: Seconds between runs.
        run: One run of the check. Errors are logged by the cron job and don't stop the loop.
        seconds_since_last_attempt: Seconds since `run` last finished, successfully or not.
        on_stop: Called once the loop ends for any reason, e.g. to stop reporting a stale
            snapshot.
    """
    job = cron.Job(name=name, interval=interval_sec, condition=lambda: True, task=run)
    task = asyncio.create_task(job())

    def on_done(task: asyncio.Task[None]) -> None:
        on_stop()
        if not task.cancelled() and (error := task.exception()) is not None:
            logger.error("The loop of check %s died", name, exc_info=error)

    task.add_done_callback(on_done)
    try:
        yield RunningCheck(
            name=name,
            task=task,
            interval_sec=interval_sec,
            seconds_since_last_attempt=seconds_since_last_attempt,
        )
    finally:
        # A loop that already died was logged by `on_done`; don't re-raise its error here.
        if not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
