# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the governance module."""

import asyncio
import pytest

import aiodogstatsd

from circuitbreaker import circuit
from pytest_mock import MockerFixture

from merino import governance


CIRCUIT_NAME: str = "test-circuit"


@pytest.mark.asyncio
async def test_governing_start_shutdown() -> None:
    """Test the start and shutdown of the governing deamon."""
    governance.start()
    cron_task: asyncio.Task | None = governance.governing.cron_task

    assert cron_task is not None

    governance.shutdown()
    await asyncio.sleep(0)  # yield to let other tasks to run.

    assert cron_task.cancelled()

    # Shutdown an inactive daemon should not raise
    governance.shutdown()


@circuit(name=CIRCUIT_NAME, failure_threshold=1, recovery_timeout=100, expected_exception=KeyError)
def dummy() -> None:
    """Attached a test circuit breaker to this dummy function."""
    raise KeyError()


@pytest.mark.asyncio
async def test_governing_metrics(mocker: MockerFixture) -> None:
    """Test the metrics emission."""
    # "Open" the circuit breaker to emit metrics.
    try:
        dummy()
    except KeyError:
        pass

    report = mocker.patch.object(aiodogstatsd.Client, "_report")

    # This doesn't require the daemon running.
    await governance.governing.cron()

    # Check the test circuit breaker is contained in the metrics.
    # Note that there might be other circuit breakers registered in the monitor.
    expected_failure_count: int = 1
    assert (f"governance.circuits.{CIRCUIT_NAME}", expected_failure_count) in {
        (call.args[0], call.args[2]) for call in report.call_args_list
    }
