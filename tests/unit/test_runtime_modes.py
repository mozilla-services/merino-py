"""Tests for Merino runtime modes."""

from collections.abc import Callable
import json
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
from merino.providers.wcs import get_provider as get_wcs_provider
from merino.runtime import RuntimeFeature, RuntimeMode, coerce_runtime_mode, mode_enables
from tests.wcs.factories import build_provider


def _route_paths(app: FastAPI) -> set[str]:
    """Return the registered paths for a FastAPI app."""
    paths: set[str] = set()
    for route in app.routes:
        path = getattr(route, "path", None)
        if isinstance(path, str):
            paths.add(path)
    return paths


def test_runtime_mode_predicates() -> None:
    """Runtime modes enable the intended feature groups."""
    assert mode_enables(RuntimeMode.ALL, RuntimeFeature.REGULAR_API)
    assert mode_enables(RuntimeMode.ALL, RuntimeFeature.WCS_API)

    assert mode_enables(RuntimeMode.REGULAR, RuntimeFeature.REGULAR_API)
    assert not mode_enables(RuntimeMode.REGULAR, RuntimeFeature.WCS_API)

    assert mode_enables(RuntimeMode.WIDGET, RuntimeFeature.WCS_API)
    assert not mode_enables(RuntimeMode.WIDGET, RuntimeFeature.REGULAR_API)


def test_runtime_mode_coercion_rejects_unknown_mode() -> None:
    """Unknown runtime mode values fail fast."""
    assert coerce_runtime_mode(RuntimeMode.WIDGET) is RuntimeMode.WIDGET
    assert coerce_runtime_mode("WIDGET") is RuntimeMode.WIDGET

    for value in ("unknown", "widget", "", None):
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
    assert "WIDGET" in result.stderr


@pytest.mark.parametrize(
    ("mode", "expected_paths", "unexpected_paths"),
    [
        (
            RuntimeMode.ALL,
            {"/__heartbeat__", "/api/v1/suggest", "/api/v1/wcs/matches"},
            set(),
        ),
        (
            RuntimeMode.REGULAR,
            {"/__heartbeat__", "/api/v1/suggest"},
            {"/api/v1/wcs/matches"},
        ),
        (
            RuntimeMode.WIDGET,
            {"/__heartbeat__", "/api/v1/wcs/matches"},
            {"/api/v1/suggest"},
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
        (RuntimeMode.ALL, ["suggest", "providers", "wcs"]),
        (RuntimeMode.REGULAR, ["suggest", "providers"]),
        (RuntimeMode.WIDGET, ["wcs"]),
    ],
)
def test_create_app_registers_openapi_tags_by_mode(
    mode: RuntimeMode, expected_tags: list[str]
) -> None:
    """The app factory exposes only OpenAPI tags for enabled feature groups."""
    tags = [tag["name"] for tag in create_app(mode).openapi_tags or []]

    assert tags == expected_tags


@pytest.mark.parametrize("mode", [RuntimeMode.ALL, RuntimeMode.REGULAR, RuntimeMode.WIDGET])
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


def test_widget_mode_serves_wcs_and_dockerflow_only() -> None:
    """Widget mode serves WCS and Dockerflow while regular API routes 404."""
    app = create_app(RuntimeMode.WIDGET)
    provider = build_provider()
    app.dependency_overrides[get_wcs_provider] = lambda: provider

    client = TestClient(app)

    assert client.get("/__heartbeat__").status_code == 200
    assert client.get("/api/v1/suggest", params={"q": "firefox"}).status_code == 404
    assert client.get("/api/v1/wcs/matches", params={"date": "2026-06-15"}).status_code == 200


def test_widget_mode_does_not_import_regular_routes() -> None:
    """Widget mode avoids regular-only router imports."""
    script = """
import json
import sys

import merino.main

regular_route_modules = [
    "merino.web.api_v1",
]
api_paths = sorted(
    route.path
    for route in merino.main.app.routes
    if hasattr(route, "path") and route.path.startswith("/api/v1")
)
print(
    json.dumps(
        {
            "regular_route_modules": {
                module_name: module_name in sys.modules for module_name in regular_route_modules
            },
            "api_paths": api_paths,
        },
        sort_keys=True,
    )
)
"""
    env = os.environ.copy()
    env["MERINO_RUNTIME__MODE"] = RuntimeMode.WIDGET.value
    # Fixed argv, shell=False, no untrusted input.
    result = subprocess.run(  # nosec B603
        [sys.executable, "-c", script],
        cwd=Path(__file__).parents[2],
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout.splitlines()[-1])
    assert output["regular_route_modules"] == {
        "merino.web.api_v1": False,
    }
    assert output["api_paths"] == [
        "/api/v1/wcs/live",
        "/api/v1/wcs/matches",
        "/api/v1/wcs/teams",
        "/api/v1/wcs/watch-links",
    ]


def test_regular_mode_serves_regular_api_without_wcs(mocker: MockerFixture) -> None:
    """Regular mode serves regular API routes while WCS routes 404."""
    import merino.main as main
    from merino.providers.suggest import get_providers as get_suggest_providers
    from tests.integration.api.v1.fake_providers import FakeProviderFactory

    async def configure_metrics() -> None:
        pass

    async def close_metrics_client() -> None:
        pass

    async def start_regular(cleanup_callbacks) -> None:
        pass

    async def start_wcs(cleanup_callbacks) -> None:
        raise AssertionError("WCS services should not start in REGULAR mode")

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
    wcs_start = mocker.patch.object(main, "_start_wcs_services", side_effect=start_wcs)
    governance_start = mocker.patch.object(main, "_start_governance", side_effect=start_governance)

    app = create_app(RuntimeMode.REGULAR)
    app.dependency_overrides[get_suggest_providers] = get_fake_providers

    with TestClient(app) as client:
        assert client.get("/__heartbeat__").status_code == 200
        response = client.get("/api/v1/suggest", params={"q": "nonsponsored"})
        assert response.status_code == 200
        assert response.json()["suggestions"][0]["full_keyword"] == "nonsponsored"
        assert client.get("/api/v1/wcs/matches", params={"date": "2026-06-15"}).status_code == 404

    regular_start.assert_awaited_once()
    wcs_start.assert_not_awaited()
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
                "wcs_start",
                "governance_start",
                "governance_shutdown",
                "wcs_shutdown",
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
        (
            RuntimeMode.WIDGET,
            [
                "logging_start",
                "sentry_start",
                "metrics_start",
                "wcs_start",
                "wcs_shutdown",
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

    async def start_wcs(cleanup_callbacks) -> None:
        events.append("wcs_start")
        cleanup_callbacks.append(record("wcs_shutdown"))

    def start_governance(cleanup_callbacks) -> None:
        events.append("governance_start")
        cleanup_callbacks.append(record("governance_shutdown"))

    mocker.patch.object(main, "configure_logging", side_effect=record("logging_start"))
    mocker.patch.object(main, "configure_sentry", side_effect=record("sentry_start"))
    mocker.patch.object(main, "configure_metrics", side_effect=configure_metrics)
    mocker.patch.object(main, "_close_metrics_client", side_effect=close_metrics_client)
    mocker.patch.object(main, "_start_regular_services", side_effect=start_regular)
    mocker.patch.object(main, "_start_wcs_services", side_effect=start_wcs)
    mocker.patch.object(main, "_start_governance", side_effect=start_governance)

    with TestClient(create_app(mode)):
        pass

    assert events == expected_events
