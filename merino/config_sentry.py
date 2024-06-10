"""Sentry Configuration"""

import json
import logging

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration
from sentry_sdk.types import Event, Hint

from merino.config import settings
from merino.utils.version import fetch_app_version_from_file

logger = logging.getLogger(__name__)

REDACTED_TEXT = "[REDACTED]"


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


def strip_sensitive_data(event: Event, hint: Hint) -> Event | None:
    """Filter out sensitive data from Sentry events."""
    #  See: https://docs.sentry.io/platforms/python/configuration/filtering/
    if event.get("request", {}).get("query_string", {}):
        event["request"]["query_string"] = REDACTED_TEXT

    try:
        for entry in event["exception"]["values"][0]["stacktrace"]["frames"]:
            if entry["vars"].get("q"):
                entry["vars"]["q"] = REDACTED_TEXT
            if entry["vars"].get("query"):
                entry["vars"]["query"] = REDACTED_TEXT
            if entry["vars"].get("srequest"):
                entry["vars"]["srequest"] = REDACTED_TEXT
            if entry["vars"].get("values", {}).get("q"):
                entry["vars"]["values"]["q"] = REDACTED_TEXT
            if (
                entry["vars"].get("solved_result", [])
                and len(entry["vars"].get("solved_result", [])) > 0
            ):
                if entry["vars"]["solved_result"][0].get("q"):
                    entry["vars"]["solved_result"][0]["q"] = REDACTED_TEXT

            # Redact the query sent to Elasticsearch.
            # This just redacts all the variables that contains a part of the
            # Elasticsearch query.
            for key, value in entry["vars"].items():
                if "suggest-on-title" in json.dumps(value):
                    entry["vars"][key] = REDACTED_TEXT

    except (KeyError, IndexError) as e:
        logger.warning(
            f"Encountered KeyError or IndexError for value {e} while filtering Sentry data."
        )

    return event
