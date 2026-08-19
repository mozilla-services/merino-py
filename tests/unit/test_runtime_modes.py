"""Tests for Merino runtime modes."""

from collections.abc import Callable
import os
from pathlib import Path

# subprocess is used only for fixed-argv fresh interpreter checks.
import subprocess  # nosec B404
import sys

import pytest
from fastapi import FastAPI
from pytest_mock import MockerFixture
from starlette.testclient import TestClient

from merino.main import create_app
from merino.runtime import RuntimeFeature, RuntimeMode, coerce_runtime_mode, mode_enables


def _route_paths(app: FastAPI) -> set[str]:
    """Return the registered paths for a FastAPI app.

    Reads the OpenAPI schema rather than ``app.routes`` because starlette
    nests included routers under opaque wrapper routes, so the flat
    ``route.path`` attributes no longer surface prefixed endpoint paths.
    """
    return set(app.openapi().get("paths", {}).keys())


def test_runtime_mode_predicates() -> None:
    """Runtime modes enable the intended feature groups."""
    assert mode_enables(RuntimeMode.ALL, RuntimeFeature.REGULAR_API)
    assert mode_enables(RuntimeMode.REGULAR, RuntimeFeature.REGULAR_API)


def test_runtime_mode_coercion_rejects_unknown_mode() -> None:
    """Unknown runtime mode values fail fast."""
    assert coerce_runtime_mode(RuntimeMode.REGULAR) is RuntimeMode.REGULAR
    assert coerce_runtime_mode("REGULAR") is RuntimeMode.REGULAR

    for value in ("unknown", "regular", "", None):
        with pytest.raises(ValueError, match="runtime mode must"):
            coerce_runtime_mode(value)


def test_invalid_configured_runtime_mode_fails_startup() -> None:
    """Invalid configured runtime mode values fail config validation."""
    env = os.environ.copy()
    env["MERINO_RUNTIME__MODE"] = "bogus"
    # Fixed argv, shell=False, no untrusted input.
    result = subprocess.run(  # nosec B603
        [sys.executable, "-c", "import merino.main"],
        cwd=Path(__file__).parents[2],
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "runtime.mode" in result.stderr
    assert "ALL" in result.stderr
    assert "REGULAR" in result.stderr


@pytest.mark.parametrize(
    ("mode", "expected_paths", "unexpected_paths"),
    [
        (
            RuntimeMode.ALL,
            {"/__heartbeat__", "/api/v1/suggest"},
            set(),
        ),
        (
            RuntimeMode.REGULAR,
            {"/__heartbeat__", "/api/v1/suggest"},
            set(),
        ),
    ],
)
def test_create_app_registers_routes_by_mode(
    mode: RuntimeMode, expected_paths: set[str], unexpected_paths: set[str]
) -> None:
    """The app factory includes only the routers enabled by the runtime mode."""
    paths = _route_paths(create_app(mode))

    assert expected_paths <= paths
    assert not unexpected_paths & paths


@pytest.mark.parametrize(
    ("mode", "expected_tags"),
    [
        (RuntimeMode.ALL, ["suggest", "providers"]),
        (RuntimeMode.REGULAR, ["suggest", "providers"]),
    ],
)
def test_create_app_registers_openapi_tags_by_mode(
    mode: RuntimeMode, expected_tags: list[str]
) -> None:
    """The app factory exposes only OpenAPI tags for enabled feature groups."""
    tags = [tag["name"] for tag in create_app(mode).openapi_tags or []]

    assert tags == expected_tags


@pytest.mark.parametrize("mode", [RuntimeMode.ALL, RuntimeMode.REGULAR])
def test_create_app_registers_same_middleware_by_mode(mode: RuntimeMode) -> None:
    """Runtime modes keep the existing middleware stack unchanged."""
    middleware_names = [
        getattr(middleware.cls, "__name__", repr(middleware.cls))
        for middleware in create_app(mode).user_middleware
    ]

    assert middleware_names == [
        "LoggingMiddleware",
        "UserAgentMiddleware",
        "GeolocationMiddleware",
        "FeatureFlagsMiddleware",
        "CorrelationIdMiddleware",
        "MetricsMiddleware",
        "CORSMiddleware",
    ]


def test_regular_mode_serves_regular_api(mocker: MockerFixture) -> None:
    """Regular mode serves the regular API routes."""
    import merino.main as main
    from merino.providers.suggest import get_providers as get_suggest_providers
    from tests.integration.api.v1.fake_providers import FakeProviderFactory

    async def configure_metrics() -> None:
        pass

    async def close_metrics_client() -> None:
        pass

    async def start_regular(cleanup_callbacks) -> None:
        pass

    def start_governance(cleanup_callbacks) -> None:
        pass

    async def get_fake_providers():
        provider = FakeProviderFactory.nonsponsored(enabled_by_default=True)
        return {"non-sponsored": provider}, [provider]

    mocker.patch.object(main, "configure_logging")
    mocker.patch.object(main, "configure_sentry")
    mocker.patch.object(main, "configure_metrics", side_effect=configure_metrics)
    mocker.patch.object(main, "_close_metrics_client", side_effect=close_metrics_client)
    regular_start = mocker.patch.object(main, "_start_regular_services", side_effect=start_regular)
    governance_start = mocker.patch.object(main, "_start_governance", side_effect=start_governance)

    app = create_app(RuntimeMode.REGULAR)
    app.dependency_overrides[get_suggest_providers] = get_fake_providers

    with TestClient(app) as client:
        assert client.get("/__heartbeat__").status_code == 200
        response = client.get("/api/v1/suggest", params={"q": "nonsponsored"})
        assert response.status_code == 200
        assert response.json()["suggestions"][0]["full_keyword"] == "nonsponsored"

    regular_start.assert_awaited_once()
    governance_start.assert_called_once()


@pytest.mark.asyncio
async def test_cleanup_callbacks_ignore_non_awaitable_return_values() -> None:
    """Cleanup callbacks may return incidental values."""
    import merino.main as main

    events: list[str] = []

    def cleanup() -> object:
        events.append("cleanup")
        return object()

    await main._run_cleanup_callbacks([cleanup])

    assert events == ["cleanup"]


@pytest.mark.parametrize(
    ("mode", "expected_events"),
    [
        (
            RuntimeMode.ALL,
            [
                "logging_start",
                "sentry_start",
                "metrics_start",
                "regular_start",
                "governance_start",
                "governance_shutdown",
                "regular_shutdown",
                "metrics_shutdown",
            ],
        ),
        (
            RuntimeMode.REGULAR,
            [
                "logging_start",
                "sentry_start",
                "metrics_start",
                "regular_start",
                "governance_start",
                "governance_shutdown",
                "regular_shutdown",
                "metrics_shutdown",
            ],
        ),
    ],
)
def test_lifespan_starts_and_stops_services_by_mode(
    mocker: MockerFixture,
    mode: RuntimeMode,
    expected_events: list[str],
) -> None:
    """The lifespan initializes and cleans up only services enabled for the mode."""
    import merino.main as main

    events: list[str] = []

    def record(event: str) -> Callable[..., None]:
        def _record(*args, **kwargs) -> None:
            events.append(event)

        return _record

    async def configure_metrics() -> None:
        events.append("metrics_start")

    async def close_metrics_client() -> None:
        events.append("metrics_shutdown")

    async def start_regular(cleanup_callbacks) -> None:
        events.append("regular_start")
        cleanup_callbacks.append(record("regular_shutdown"))

    def start_governance(cleanup_callbacks) -> None:
        events.append("governance_start")
        cleanup_callbacks.append(record("governance_shutdown"))

    mocker.patch.object(main, "configure_logging", side_effect=record("logging_start"))
    mocker.patch.object(main, "configure_sentry", side_effect=record("sentry_start"))
    mocker.patch.object(main, "configure_metrics", side_effect=configure_metrics)
    mocker.patch.object(main, "_close_metrics_client", side_effect=close_metrics_client)
    mocker.patch.object(main, "_start_regular_services", side_effect=start_regular)
    mocker.patch.object(main, "_start_governance", side_effect=start_governance)

    with TestClient(create_app(mode)):
        pass

    assert events == expected_events
