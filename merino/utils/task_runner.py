"""A utility module to facilitate running & managing asyncio Tasks."""

import logging
from asyncio import ALL_COMPLETED, Task, wait
from typing import Callable, Optional

from merino.metrics import Client

logger = logging.getLogger(__name__)

# Type for timeout callback
TimeoutCallback = Callable[[list[Task]], None]


async def gather(
    tasks: list[Task],
    *,
    timeout: Optional[float] = None,
    timeout_cb: Optional[TimeoutCallback] = None,
) -> tuple[list[Task], list[Task]]:
    """Run a list of tasks to their completion, gather all the completed tasks whenever
    they finish. If a timeout is specified, all the pending tasks will be cancelled
    if the timeout occurs prior to their completion.

    Args:
    - tasks: A list of Tasks.
    - timeout: A float indicating timeout (in seconds) for the entire task execution.
      If not specified, no timeout will be set.
    - timeout_cb: A callable that gets called when timeout occurs. This callback will
      be executed before the cancellation of the timeout tasks.

    Returns: a tuple of two lists: the completed tasks and the timed out tasks.

    Note that:
    - The order of the returned tasks might not be the same as the input tasks.
    - The completed tasks may contain tasks that have encountered exceptions. The caller
      can either `await` those tasks with exception handling or call `result()` or
      `exception()` on the those tasks to fetch the results (or exceptions).
    - This function shares the same semantics as `asyncio.gather()` except that it
      provides with a number of more functionalities than the latter.
    """
    if len(tasks) == 0:
        return [], []

    done, pending = await wait(tasks, timeout=timeout, return_when=ALL_COMPLETED)
    if pending:
        logger.warning("Timeout triggered in the task runner")
        if timeout_cb:
            timeout_cb(list(pending))
        for task in pending:
            logger.warning(f"Cancelling the task: {task.get_name()} due to timeout")
            task.cancel()

    return list(done), list(pending)


def metrics_timeout_handler(client: Client, tasks: list[Task]) -> None:
    """Timeout handler to record metrics for timed out tasks"""
    for task in tasks:
        client.increment(f"providers.{task.get_name()}.query.timeout")
