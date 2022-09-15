# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import asyncio
import logging
from typing import Any

import pytest

from merino import cron


@pytest.fixture(name="numbers")
def fixture_numbers() -> list[int]:
    """Return a list containing the number 1."""
    return [1]


@pytest.fixture(name="condition")
def fixture_condition(numbers: list[int]) -> cron.Condition:
    """Return a condition for a cron job."""

    def should_run() -> bool:
        """Returns True if there are no more than 2 items in numbers."""
        return len(numbers) <= 2

    return should_run


@pytest.fixture(name="task")
def fixture_task(numbers: list[int]) -> cron.Task:
    """Return a task for a cron job."""

    async def add_number() -> None:
        """Adds a new number to the list."""
        new_number = numbers[-1] + 1

        if new_number == 2:
            numbers.append(3)
            raise ValueError("Number 2 is not valid. Added 3 instead.")

        numbers.append(new_number)

    return add_number


@pytest.fixture(name="cron_job")
def fixture_cron_job(condition: cron.Condition, task: cron.Task) -> cron.Job:
    """Return a cron job."""

    return cron.Job(name="create_numbers", interval=0.1, condition=condition, task=task)


@pytest.mark.asyncio
async def test_cron(caplog: Any, cron_job: cron.Job, numbers: list[int]) -> None:
    """Test for the CronJob implementation."""

    caplog.set_level(logging.INFO)

    # Schedule the task like adm.Provider does it
    cron_task = asyncio.create_task(cron_job())

    # Cancel the task after 0.5 seconds
    await asyncio.sleep(0.5)
    cron_task.cancel()

    assert numbers == [1, 3, 4]

    # Verify log messages for the different branches
    assert caplog.record_tuples == [
        (
            "merino.cron",
            logging.WARNING,
            "Cron: failed to run task create_numbers",
        ),
        (
            "merino.cron",
            logging.INFO,
            "Cron: successfully ran task create_numbers",
        ),
    ]
    error_message = caplog.records[0].__dict__["error message"]
    assert error_message == "Number 2 is not valid. Added 3 instead."
