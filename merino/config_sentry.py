import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

from merino.config import settings


def configure_sentry():  # pragma: no cover
    """
    Configure and initialize Sentry integration.
    """

    if settings.sentry.mode == "disabled":
        return

    sentry_sdk.init(
        dsn=settings.sentry.dsn,
        integrations=[
            StarletteIntegration(),
            FastApiIntegration(),
        ],
        debug="debug" == settings.sentry.mode,
        environment=settings.sentry.env,
        # Set traces_sample_rate to 1.0 to capture 100%
        # of transactions for performance monitoring.
        # We recommend adjusting this value in production,
        traces_sample_rate=settings.sentry.traces_sample_rate,
    )
