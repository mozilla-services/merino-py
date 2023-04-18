"""Sentry Configuration"""

import logging
from typing import Any

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

from merino.config import settings
from merino.exceptions import BackendError
from merino.utils.version import fetch_app_version_from_file

logger = logging.getLogger(__name__)


def configure_sentry() -> None:  # pragma: no cover
    """Configure and initialize Sentry integration."""
    if settings.sentry.mode == "disabled":
        return
    # This is the SHA-1 hash of the HEAD of the current branch stored in version.json file.
    version_sha = fetch_app_version_from_file().commit
    sentry_sdk.init(
        dsn=settings.sentry.dsn,
        integrations=[
            StarletteIntegration(),
            FastApiIntegration(),
        ],
        release=version_sha,
        debug="debug" == settings.sentry.mode,
        before_send=strip_sensitive_data,
        environment=settings.sentry.env,
        # Set traces_sample_rate to 1.0 to capture 100%
        # of transactions for performance monitoring.
        # We recommend adjusting this value in production,
        traces_sample_rate=settings.sentry.traces_sample_rate,
    )


def strip_sensitive_data(event: dict, hint: dict) -> Any:
    """Filter out sensitive data from Sentry events."""
    #  See: https://docs.sentry.io/platforms/python/configuration/filtering/
    if event["request"]["query_string"]:
        event["request"]["query_string"] = "query_str_foo"

    if "exc_info" in hint:
        exc_type, exc_value, tb = hint["exc_info"]
        if isinstance(exc_value, RuntimeError) or isinstance(exc_value, BackendError):
            for entry in event["exception"]["values"][0]["stacktrace"]["frames"]:
                try:
                    if entry["vars"].get("q"):
                        entry["vars"]["q"] = "vars_foo"
                    if entry["vars"].get("query"):
                        entry["vars"]["query"] = "picked_repl"
                    if entry["vars"].get("srequest"):
                        entry["vars"]["srequest"] = "sreq_repl"
                    if entry["vars"]["values"].get("q"):
                        entry["vars"]["values"]["q"] = "vars_values_foo"
                    if entry["vars"]["solved_result"][0].get("q"):
                        entry["vars"]["solved_result"][0]["q"] = "solved_foo"

                except KeyError as e:
                    logger.debug(
                        f"Sentry filtering RuntimeError query value not found: {e}"
                    )
                    continue

    return event
