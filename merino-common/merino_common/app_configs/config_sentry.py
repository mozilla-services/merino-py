"""Sentry Configuration"""

import json
import logging
from collections.abc import Mapping

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration
from sentry_sdk.types import Event, Hint

from merino_common.utils.version import fetch_app_version_from_file

logger = logging.getLogger(__name__)

REDACTED_TEXT = "[REDACTED]"


def configure_sentry(
    mode: str,
    dsn: str,
    env: str,
    traces_sample_rate: float,
    *,
    default_tags: Mapping[str, object] | None = None,
) -> None:  # pragma: no cover
    """Configure and initialize Sentry integration.

    Args:
        mode: One of "release", "debug", or "disabled". When "disabled" no Sentry
            client is initialized.
        dsn: Sentry DSN. Ignored when ``mode == "disabled"``.
        env: Sentry environment tag (e.g. "prod", "stage", "dev").
        traces_sample_rate: Fraction of transactions to capture for performance
            monitoring, in [0.0, 1.0].
    """
    if mode == "disabled":
        return
    # This is the SHA-1 hash of the HEAD of the current branch stored in version.json file.
    version_sha = fetch_app_version_from_file().commit
    sentry_sdk.init(
        dsn=dsn,
        integrations=[
            StarletteIntegration(),
            FastApiIntegration(),
        ],
        release=version_sha,
        debug="debug" == mode,
        before_send=strip_sensitive_data,
        environment=env,
        # Set traces_sample_rate to 1.0 to capture 100%
        # of transactions for performance monitoring.
        # We recommend adjusting this value in production,
        traces_sample_rate=traces_sample_rate,
    )
    if default_tags:
        sentry_sdk.set_tags(default_tags)


def strip_sensitive_data(event: Event, hint: Hint) -> Event | None:
    """Filter out sensitive data from Sentry events."""
    #  See: https://docs.sentry.io/platforms/python/configuration/filtering/
    if event.get("request", {}).get("query_string", {}):
        event["request"]["query_string"] = REDACTED_TEXT

        event_exception_values = event.get("exception", {}).get("values", [])
        if len(event_exception_values):
            for entry in event_exception_values[0].get("stacktrace", {}).get("frames", []):
                vars = entry.get("vars", {})

                match vars:
                    case {"q": _}:
                        vars["q"] = REDACTED_TEXT
                    case {"srequest": _, "query": _}:
                        vars["srequest"] = REDACTED_TEXT
                        vars["query"] = REDACTED_TEXT
                    case {"query": _}:
                        vars["query"] = REDACTED_TEXT
                    case {"values": {"q": _}, "solved_result": [{"q": _}, *_]}:
                        vars["values"]["q"] = REDACTED_TEXT
                        vars["solved_result"][0]["q"] = REDACTED_TEXT
                    case {"values": {"q": _}}:
                        vars["values"]["q"] = REDACTED_TEXT
                    case _:
                        pass

                # Redact the query sent to Elasticsearch.
                # This just redacts all the variables that contains a part of the
                # Elasticsearch query.
                for key, value in entry["vars"].items():
                    if "suggest-on-title" in json.dumps(value):
                        entry["vars"][key] = REDACTED_TEXT

    event_exception_values = event.get("exception", {}).get("values", [])
    if len(event_exception_values):
        for entry in event_exception_values[0].get("stacktrace", {}).get("frames", []):
            vars = entry.get("vars", {})
            args = vars.get("args")
            if isinstance(args, dict) and "key" in args:
                args["key"] = REDACTED_TEXT

            headers = vars.get("headers")
            if isinstance(headers, dict):
                for header in headers:
                    if str(header).lower() == "ocp-apim-subscription-key":
                        headers[header] = REDACTED_TEXT

    return event
