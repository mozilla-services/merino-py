"""Unit tests for merino_hook_eye.checks."""

import asyncio
from unittest.mock import MagicMock

import pytest

from merino_hook_eye.checks import STALL_INTERVALS, run_check


class _LoopKiller(BaseException):
    """An error the cron job doesn't catch, so it ends the loop."""


async def _noop() -> None:
    """Do nothing, as a check run."""


@pytest.mark.asyncio
async def test_check_is_alive_until_it_stalls() -> None:
    """A running check is alive until its last run is older than its stall window."""
    age = 0.0
    async with run_check(
        name="test",
        interval_sec=60,
        run=_noop,
        seconds_since_last_attempt=lambda: age,
        on_stop=lambda: None,
    ) as check:
        assert check.is_alive()

        age = STALL_INTERVALS * 60 + 1
        assert not check.is_alive()


@pytest.mark.asyncio
async def test_check_stops_on_exit() -> None:
    """Leaving the context cancels the loop and calls `on_stop`."""
    on_stop = MagicMock()
    async with run_check(
        name="test",
        interval_sec=60,
        run=_noop,
        seconds_since_last_attempt=lambda: 0,
        on_stop=on_stop,
    ) as check:
        on_stop.assert_not_called()

    await asyncio.sleep(0)
    assert check.task.cancelled()
    on_stop.assert_called_once_with()


@pytest.mark.asyncio
async def test_check_loop_death_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    """A loop that dies stops the check, is logged, and doesn't fail shutdown."""
    on_stop = MagicMock()

    async def die() -> None:
        raise _LoopKiller()

    async with run_check(
        name="doomed",
        interval_sec=60,
        run=die,
        seconds_since_last_attempt=lambda: 0,
        on_stop=on_stop,
    ) as check:
        for _ in range(10):
            await asyncio.sleep(0)

        assert check.task.done()
        assert not check.is_alive()
        on_stop.assert_called_once_with()

    assert "The loop of check doomed died" in caplog.text
