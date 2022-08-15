import os

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration


def sentry_init():
    """Function for initialization of Sentry"""
    sentry_sdk.init(
        # This DSN value will be updated to reflect configuration management setup.
        # Be default, sentry tries to find this in the SENTRY_DSN environment variable.
        # Can then also remove the `import os` line.
        dsn=os.environ.get("MERINO_PY_SENTRY_DSN"),
        # Add automatic instrumentation to application. Sentry typically does this by default when
        # reading modules, but this is not auto-enabled just yet.
        # https://docs.sentry.io/platforms/python/guides/fastapi/
        integrations=[
            StarletteIntegration(),
            FastApiIntegration(),
        ],
        # Ideally want this disabled for production. Helps debug possible errors.
        debug=True,
        # This setting is ideally read from the SENTRY_ENVIRONMENT variable
        environment="development",
        # Set traces_sample_rate to 1.0 to capture 100%
        # of transactions for performance monitoring.
        # We recommend adjusting this value in production.
        traces_sample_rate=1.0,
    )
