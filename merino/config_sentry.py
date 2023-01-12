"""Sentry Configuration"""
import json
import logging
import os.path
from typing import Optional

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

from merino.config import settings
from merino.exceptions import InvalidGitRepository

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


def read_git_head_file(merino_root_dir: str) -> str:
    """Given the project root, attempt to locate and read the remote HEAD
    from the .git/HEAD file.
    """
    head_path = os.path.join(merino_root_dir, ".git", "HEAD")
    if not os.path.exists(head_path):
        message = f"Cannot identify HEAD for git repository at {head_path}"
        logger.warning(message)
        raise InvalidGitRepository(message)
    with open(head_path, "r") as head_file:
        head = head_file.read().strip()
        if head.startswith("ref: "):
            head = head[5:]
    return head


def check_git_packed_refs(head) -> Optional[str]:  # pragma: no cover
    """Check .git/packed-refs for SHA in the case garbage collection clared original
    hash in refs/heads directory.
    """
    # NOTE: In the case git has run "auto gc" (garbage collection), loose objects could be moved
    # into .git/packed-refs. This is where branch references could be moved, making it
    # important to check if the hash is stored in packed-refs. Git automatically
    # writes and updates references in refs/heads, but if that reference is not there
    # packed-refs is checked.
    # See: https://git-scm.com/book/en/v2/Git-Internals-Maintenance-and-Data-Recovery

    packed_file = os.path.join(head, ".git", "packed-refs")
    if os.path.exists(packed_file):
        with open(packed_file) as file:
            for line in file:
                line = line.rstrip()
                # Filter out lines containing # and ^
                if line and line[:1] not in ("#", "^"):
                    try:
                        # Assigns SHA to revision_sha and ref to the head
                        # directory reference passed in.
                        revision_sha, ref = line.split(" ", 1)
                    except ValueError:
                        continue
                    # If packed_ref file contains matching head reference, return.
                    if ref == head:
                        return revision_sha
    return None


def fetch_git_sha(path: str) -> str:
    """Read and capture the the git SHA hash for current HEAD of branch.
    Thus value is passed to Sentry as the release flag so that the
    version of Merino is emitted in Sentry's release tag.
    """
    # head_path captures the name of the file in refs/heads that contains hash.
    head_path: str = read_git_head_file(path)

    # check packed_refs for revision SHA. NOTE: See function notes for details.
    packed_refs: Optional[str] = check_git_packed_refs(head_path)
    if packed_refs:
        return packed_refs
    # refs_heads_path creates the path ro the file in refs/heads.
    refs_heads_path: str = os.path.join(path, ".git", *head_path.split("/"))
    # the revision_file_path is the absolute path to the SHA hash.
    revision_file_path: str = os.path.join(
        path, ".git", "refs", "heads", refs_heads_path
    )

    if not os.path.exists(revision_file_path):
        if not os.path.exists(os.path.join(path, ".git")):
            message = f"{path} does not appear to be the root of a git repository."
            logger.warning(message)
            raise InvalidGitRepository(message)

    with open(revision_file_path, "r") as sha_file:
        revision_sha = sha_file.read().strip()
        return revision_sha


def fetch_sha_hash_from_version_file(
    merino_root_path: str,
) -> Optional[str]:  # pragma: no cover
    """In production and stage, fetch the SHA hash from the version.json file.
    During deployment, this file is written and values are populated for the current
    version of Merino.
    """
    version_file_path: str = f"{merino_root_path}/version.json"
    if not os.path.exists(version_file_path):
        error_message = (
            f"version.json file does not exist at file path: {merino_root_path}"
        )
        logger.warning(error_message)
        raise FileNotFoundError(error_message)

    with open(version_file_path) as file:
        version_file: dict = json.load(file)
        commit_hash: str | None = version_file.get("commit")
    if commit_hash:
        return commit_hash
    return None
