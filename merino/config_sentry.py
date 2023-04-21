"""Sentry Configuration"""
import logging

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

from merino.config import settings
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


def strip_sensitive_data(event: dict, hint: dict) -> dict:
    """Filter out sensitive data from Sentry events."""
    #  See: https://docs.sentry.io/platforms/python/configuration/filtering/
    if event.get("request", {}).get("query_string", {}):
        event["request"]["query_string"] = ""

    if "exc_info" in hint:
        exc_type, exc_value, tb = hint["exc_info"]
        if isinstance(exc_value, Exception):
            try:
                for entry in event["exception"]["values"][0]["stacktrace"]["frames"]:
                    if entry["vars"].get("q"):
                        entry["vars"]["q"] = ""
                    if entry["vars"].get("query"):
                        entry["vars"]["query"] = ""
                    if entry["vars"].get("srequest"):
                        entry["vars"]["srequest"] = ""
                    if entry["vars"].get("values", {}).get("q"):
                        entry["vars"]["values"]["q"] = ""
                    if (
                        entry["vars"].get("solved_result", [])
                        and len(entry["vars"].get("solved_result", [])) > 0
                    ):
                        if entry["vars"]["solved_result"][0].get("q"):
                            entry["vars"]["solved_result"][0]["q"] = ""
            except KeyError as e:
                logger.warning(
                    f"Encountered KeyError for key {e} while filtering Sentry data."
                )
                pass

    return event
