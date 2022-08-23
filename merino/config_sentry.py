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
    )
