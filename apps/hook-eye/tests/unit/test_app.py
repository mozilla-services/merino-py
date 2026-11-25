"""Tests for the merino-hook-eye app factory and lifespan."""

import asyncio
import contextlib
import dataclasses
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from merino_hook_eye import app as app_module
from merino_hook_eye.app import create_app
from merino_hook_eye.ccr import follower as ccr_follower
from merino_hook_eye.ccr import metrics as ccr_metrics
from merino_hook_eye.checks import STALL_INTERVALS, RunningCheck


@pytest.fixture(autouse=True)
def _stub_global_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutralize the lifespan's logging and Sentry setup.

    `configure_logging` applies a `dictConfig`, which replaces the process-wide logging
    configuration and strips the handler `caplog` installs. Both are covered by
    merino-common's own tests.
    """
    monkeypatch.setattr(app_module, "configure_logging", lambda **kwargs: None)
    monkeypatch.setattr(app_module, "configure_sentry", lambda **kwargs: None)


@pytest.fixture
def es_client(monkeypatch: pytest.MonkeyPatch, ccr_stats_body: dict[str, Any]) -> MagicMock:
    """Replace the follower client the CCR follower check builds with a stand-in."""
    client = MagicMock()
    client.ccr.stats = AsyncMock(return_value=MagicMock(body=ccr_stats_body))
    client.close = AsyncMock()
    monkeypatch.setattr(ccr_follower, "build_client", lambda: client)
    return client


def _running_checks(client: TestClient) -> list[RunningCheck]:
    """Return the checks the app's lifespan started."""
    checks: list[RunningCheck] = client.app.state.checks  # type: ignore[attr-defined]
    return checks


def test_lifespan_scrapes_and_closes_client(es_client: MagicMock) -> None:
    """The lifespan scrapes on startup, then drops the snapshot and closes the client."""
    with TestClient(create_app()) as client:
        portal = client.portal
        assert portal is not None
        # Give the cron task a chance to run its first tick.
        for _ in range(50):
            if ccr_metrics.latest() is not None:
                break
            portal.call(asyncio.sleep, 0.01)

        assert [check.name for check in _running_checks(client)] == ["ccr_follower"]
        assert ccr_metrics.latest() is not None
        assert client.get("/__heartbeat__").status_code == 200
        assert client.get("/__lbheartbeat__").status_code == 200

    assert ccr_metrics.latest() is None
    es_client.ccr.stats.assert_awaited()
    es_client.close.assert_awaited_once()


def test_lifespan_skips_disabled_checks(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A disabled check never starts, and the heartbeat passes with nothing to watch."""
    # `setitem`, not `setattr`: undoing `setattr` on the Dynaconf box deletes the key.
    monkeypatch.setitem(app_module.settings.ccr_follower, "enabled", False)
    build_client = MagicMock()
    monkeypatch.setattr(ccr_follower, "build_client", build_client)

    with TestClient(create_app()) as client:
        assert _running_checks(client) == []
        assert client.get("/__heartbeat__").status_code == 200

    build_client.assert_not_called()
    assert "No checks are enabled" in caplog.text


def test_heartbeat_fails_when_a_check_stops(es_client: MagicMock) -> None:
    """Once a check's loop ends, the heartbeat fails and the check's snapshot is dropped."""
    with TestClient(create_app()) as client:
        portal = client.portal
        assert portal is not None
        portal.call(_cancel_and_wait, _running_checks(client)[0].task)

        assert client.get("/__heartbeat__").status_code == 503
        assert ccr_metrics.latest() is None


def test_heartbeat_fails_when_a_check_stalls(es_client: MagicMock) -> None:
    """The heartbeat fails when a check hasn't finished a run within its stall window."""
    with TestClient(create_app()) as client:
        [check] = _running_checks(client)
        stall_after = STALL_INTERVALS * check.interval_sec

        def with_age(age: float) -> None:
            stalled = dataclasses.replace(check, seconds_since_last_attempt=lambda: age)
            client.app.state.checks = [stalled]  # type: ignore[attr-defined]

        with_age(stall_after - 1)
        assert client.get("/__heartbeat__").status_code == 200

        with_age(stall_after + 1)
        assert client.get("/__heartbeat__").status_code == 503


def test_heartbeat_replaces_shared_dockerflow_route() -> None:
    """Hook-eye's heartbeat replaces the shared one; the other Dockerflow endpoints remain."""
    paths = create_app().openapi()["paths"]

    assert "died or stalled" in paths["/__heartbeat__"]["get"]["description"]
    assert {"/__lbheartbeat__", "/__version__"} <= paths.keys()


def test_every_check_has_a_setting() -> None:
    """Each registered check has a settings section with an `enabled` switch."""
    for name in app_module.CHECKS:
        assert isinstance(app_module.settings[name].enabled, bool)


async def _cancel_and_wait(task: asyncio.Task[None]) -> None:
    """Cancel `task` and wait for it, and its done callbacks, to finish."""
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
    await asyncio.sleep(0)
