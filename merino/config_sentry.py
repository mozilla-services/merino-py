"""Sentry Configuration"""

import logging
import os.path

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

from merino.config import settings

logger = logging.getLogger(__name__)


def configure_sentry() -> None:  # pragma: no cover
    """Configure and initialize Sentry integration."""
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


def fetch_git_sha(path):  # pragma: no cover
    """Read and capture the the git SHA hash for the given path.
    It is valuable to pass this value to Sentry so the accurate
    version of Merino is emitted in Sentry's release tag.
    """
    head_path = os.path.join(path, ".git", "HEAD")
    if not os.path.exists(head_path):
        logger.warning(f"Cannot identify HEAD for git repository at {head_path}")
        raise InvalidGitRepository(
            f"Cannot identify HEAD for git repository at {head_path}"
        )
    with open(head_path, "r") as file_path:
        head = file_path.read().strip()

    if head.startswith("ref: "):
        head = head[5:]
        revision_file = os.path.join(path, ".git", *head.split("/"))
        return revision_file
    else:
        return head


class InvalidGitRepository(Exception):
    """Exception to handle invalid Git Repository."""

    ...
