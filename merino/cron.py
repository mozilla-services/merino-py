"""Utility Class that can be used to implement cron jobs based on asyncio tasks"""

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import asyncio
import logging
import time
from typing import Protocol

logger = logging.getLogger(__name__)


class Condition(Protocol):
    """Check whether the cron task should run."""

    def __call__(self) -> bool:  # pragma: no cover
        # noqa: D102
        ...


class Task(Protocol):
    """Task for the cron job."""

    async def __call__(self) -> None:  # pragma: no cover
        # noqa: D102
        ...


class Job:
    """Periodally run a given task if a given condition is met."""

    name: str
    interval: float
    condition: Condition
    task: Task

    def __init__(self, *, name: str, interval: float, condition: Condition, task: Task) -> None:
        self.name = name
        self.interval = interval
        self.condition = condition
        self.task = task

    async def __call__(self) -> None:
        # noqa: D102
        last_tick: float = time.time()

        while True:
            if self.condition():
                begin = time.perf_counter()
                try:
                    await self.task()
                except Exception as e:
                    logger.warning(
                        f"Cron: failed to run task {self.name}",
                        extra={"error message": f"{e}"},
                    )
                else:
                    logger.info(
                        f"Cron: successfully ran task {self.name}",
                        extra={"duration": time.perf_counter() - begin},
                    )

            sleep_duration = max(0, self.interval + last_tick - time.time())
            await asyncio.sleep(sleep_duration)
            last_tick = time.time()
