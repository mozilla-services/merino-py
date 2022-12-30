"""Sentry Configuration"""

import logging
import os.path

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

from merino.config import settings

logger = logging.getLogger(__name__)
MERINO_PATH = os.path.dirname(os.path.abspath(__name__))


def configure_sentry() -> None:  # pragma: no cover
    """Configure and initialize Sentry integration."""
    if settings.sentry.mode == "disabled":
        return
    git_hash = fetch_git_sha(MERINO_PATH)
    sentry_sdk.init(
        dsn=settings.sentry.dsn,
        integrations=[
            StarletteIntegration(),
            FastApiIntegration(),
        ],
        release=git_hash,
        debug="debug" == settings.sentry.mode,
        environment=settings.sentry.env,
        # Set traces_sample_rate to 1.0 to capture 100%
        # of transactions for performance monitoring.
        # We recommend adjusting this value in production,
        traces_sample_rate=settings.sentry.traces_sample_rate,
    )


def fetch_git_sha(path) -> str:  # pragma: no cover
    """Read and capture the the git SHA hash for current HEAD of branch.
    Thus value is passed to Sentry as the release flag so that the
    version of Merino is emitted in Sentry's release tag.
    """
    head_path = os.path.join(path, ".git", "HEAD")
    if not os.path.exists(head_path):
        logger.warning(f"Cannot identify HEAD for git repository at {head_path}")
        raise InvalidGitRepository(
            f"Cannot identify HEAD for git repository at {head_path}"
        )
    with open(head_path, "r") as head_file:
        head = head_file.read().strip()

    if head.startswith("ref: "):
        head = head.lstrip("ref: ")

    refs_heads_path = os.path.join(path, ".git", *head.split("/"))
    revision_file_path = os.path.join(path, ".git", "refs", "heads", refs_heads_path)

    if not os.path.exists(revision_file_path):
        if not os.path.exists(os.path.join(path, ".git")):
            logger.warning(
                f"{path} does not appear to be the root of a git repository."
            )
            raise InvalidGitRepository(
                f"{path} does not appear to be the root of a git repository."
            )

    with open(revision_file, "r") as sha_file:
        return sha_file.read().strip()


class InvalidGitRepository(Exception):
    """Exception to handle invalid Git Repository."""

    ...
