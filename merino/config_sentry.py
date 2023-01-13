"""Sentry Configuration"""
import json
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
    # This is the SHA-1 hash of the HEAD of the current branch.
    version_sha: str | None = fetch_sha_hash_from_version_file(MERINO_PATH)
    sentry_sdk.init(
        dsn=settings.sentry.dsn,
        integrations=[
            StarletteIntegration(),
            FastApiIntegration(),
        ],
        release=version_sha,
        debug="debug" == settings.sentry.mode,
        environment=settings.sentry.env,
        # Set traces_sample_rate to 1.0 to capture 100%
        # of transactions for performance monitoring.
        # We recommend adjusting this value in production,
        traces_sample_rate=settings.sentry.traces_sample_rate,
    )


def fetch_sha_hash_from_version_file(
    merino_root_path: str,
) -> str | None:
    """Fetch the SHA hash from the version.json file.
    During deployment, this file is written and values are
    populated for the current version of Merino in production and staging.
    """
    version_file_path: str = os.path.join(merino_root_path, "version.json")
    if not os.path.exists(version_file_path):
        error_message = (
            f"version.json file does not exist at file path: {merino_root_path}"
        )
        logger.warning(error_message)
        raise FileNotFoundError(error_message)

    with open(version_file_path) as file:
        version_file: dict = json.load(file)
        commit_hash: str | None = version_file.get("commit")
    return commit_hash
