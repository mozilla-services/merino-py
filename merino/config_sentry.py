"""Sentry Configuration"""

from typing import Any

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

from merino.config import settings
from merino.utils.version import fetch_app_version_from_file


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
        before_send=strip_sensitive_data,  # type: ignore [arg-type]
        environment=settings.sentry.env,
        # Set traces_sample_rate to 1.0 to capture 100%
        # of transactions for performance monitoring.
        # We recommend adjusting this value in production,
        traces_sample_rate=settings.sentry.traces_sample_rate,
    )


def strip_sensitive_data(event) -> Any:
    """Filter out sensitive data from Sentry events."""
    #  See: https://docs.sentry.io/platforms/python/configuration/filtering/
    if event.q:
        delattr(event, "q")
    if event.query:
        delattr(event, "query")
    return event
