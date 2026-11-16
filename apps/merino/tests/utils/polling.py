"""Helpers for waiting on conditions that become true asynchronously."""

import time
from collections.abc import Callable


def eventually[T](
    check: Callable[[], T],
    timeout: float = 30,
    interval: float = 0.5,
    message: str | None = None,
) -> T:
    """Return the first truthy result of check, polling every interval until timeout.

    Raise AssertionError with message, or a generic one, if the timeout elapses first.
    """
    deadline = time.monotonic() + timeout
    while not (result := check()):
        if time.monotonic() >= deadline:
            raise AssertionError(message or f"Condition not met within {timeout}s")
        time.sleep(interval)
    return result
