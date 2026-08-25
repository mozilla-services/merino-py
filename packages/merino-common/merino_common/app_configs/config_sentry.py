"""Sentry Configuration"""

import json
import logging
from collections.abc import Iterator, Mapping
from typing import Any

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.logging import ignore_logger
from sentry_sdk.integrations.starlette import StarletteIntegration
from sentry_sdk.types import Event, Hint

from merino_common.utils.version import fetch_app_version_from_file

logger = logging.getLogger(__name__)

REDACTED_TEXT = "[REDACTED]"

# Keys whose values are, or contain, a raw user query. Matched at any depth of a nested
# structure: request bodies, breadcrumb data and log record extras.
SENSITIVE_KEYS: frozenset[str] = frozenset({"q", "query", "search_terms", "submission"})

# Modules on the search term submission & sanitization path. Every frame local in these
# modules is redacted unless its name is in `SAFE_VAR_NAMES`.
SEARCH_TERM_MODULES: tuple[str, ...] = (
    "merino.message_handlers.search_terms",
    "merino.middleware.logging",
    "merino.utils.log_data_creators",
    "merino_common.models.suggest_logging",
    "merino_common.utils.async_batch_queue",
    "merino_common.utils.query_processing",
    "merino_fleece",
)

# The same modules as file paths, for frames where Sentry reports a filename but no module.
SEARCH_TERM_PATHS: tuple[str, ...] = tuple(
    module.replace(".", "/") for module in SEARCH_TERM_MODULES
)

# Frame locals in `SEARCH_TERM_MODULES` are redacted wholesale. On that path a local holds
# a user query, or something derived from one, often enough that enumerating the exceptions
# is not worth the risk of missing one. Name a local here to opt it back in for debugging.
EXEMPT_VAR_NAMES: frozenset[str] = frozenset()

# Substrings that identify a serialized search term payload wherever it surfaces. Used for
# frames outside `SEARCH_TERM_MODULES` -- httpx, FastAPI, pydantic, Pub/Sub and
# Elasticsearch all carry the payload in their own locals -- and for exception messages.
PAYLOAD_MARKERS: tuple[str, ...] = (
    "search_terms",
    "SuggestRequestParams",
    "SearchTermsSubmission",
    "SanitizedSearchTermLog",
    # The Elasticsearch query built from a Wikipedia suggest query.
    "suggest-on-title",
)

# Loggers that exist solely to emit structured search term records to stdout for downstream
# ingestion. Their `extra=` payloads carry raw queries, and Sentry's logging integration
# would otherwise turn every record into a breadcrumb attached to later events.
SEARCH_TERM_LOGGERS: tuple[str, ...] = ("web.suggest.request", "web.suggest.sanitized")


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
    ignore_search_term_loggers()
    if default_tags:
        sentry_sdk.set_tags(default_tags)


def ignore_search_term_loggers() -> None:
    """Stop the search term loggers from feeding Sentry breadcrumbs and events.

    These loggers emit a raw user query in the record's ``extra``, which Sentry's logging
    integration copies into ``breadcrumb["data"]``. Without this, one suggest request log
    attaches a query to every event the process sends afterwards. They carry no diagnostic
    value in Sentry, so drop them at the source rather than scrub them per event.
    """
    for name in SEARCH_TERM_LOGGERS:
        ignore_logger(name)


def _redact_keys(value: Any) -> None:
    """Redact the values of `SENSITIVE_KEYS` anywhere within `value`, in place.

    Recursion is unbounded by design: Sentry serializes the event before `before_send` runs,
    so `value` is an acyclic structure of primitives already capped at the SDK's max depth.
    """
    if isinstance(value, dict):
        for key, item in list(value.items()):
            if isinstance(key, str) and key in SENSITIVE_KEYS:
                value[key] = REDACTED_TEXT
            else:
                _redact_keys(item)
    elif isinstance(value, list):
        for item in value:
            _redact_keys(item)


def _contains_payload(value: Any) -> bool:
    """Return whether `value` looks like a serialized search term payload.

    Fails closed: a value that cannot be serialized is treated as sensitive.
    """
    try:
        serialized = json.dumps(value, default=str)
    except TypeError, ValueError:
        return True
    return any(marker in serialized for marker in PAYLOAD_MARKERS)


def _iter_frames(event: Event) -> Iterator[dict[str, Any]]:
    """Yield every stack frame in the event.

    Covers all exception values, not just the first: `raise X from Y` reports two, and the
    frames of the raised exception are in the last one. Thread stacktraces are included as
    well, since a `logger.error()` call without `exc_info` reports its locals there.
    """
    containers: list[dict[str, Any]] = [
        *event.get("exception", {}).get("values", []),
        *event.get("threads", {}).get("values", []),
    ]
    for container in containers:
        stacktrace = container.get("stacktrace")
        if not isinstance(stacktrace, dict):
            continue
        yield from stacktrace.get("frames") or []


def _is_search_term_frame(frame: dict[str, Any]) -> bool:
    """Return whether the frame belongs to the search term submission path."""
    module = frame.get("module")
    if isinstance(module, str) and module.startswith(SEARCH_TERM_MODULES):
        return True
    filename = frame.get("filename")
    return isinstance(filename, str) and any(path in filename for path in SEARCH_TERM_PATHS)


def _redact_suggest_vars(frame_vars: dict[str, Any]) -> None:
    """Redact the suggest query out of the frame locals that are known to carry it."""
    match frame_vars:
        case {"q": _}:
            frame_vars["q"] = REDACTED_TEXT
        case {"srequest": _, "query": _}:
            frame_vars["srequest"] = REDACTED_TEXT
            frame_vars["query"] = REDACTED_TEXT
        case {"query": _}:
            frame_vars["query"] = REDACTED_TEXT
        case {"values": {"q": _}, "solved_result": [{"q": _}, *_]}:
            frame_vars["values"]["q"] = REDACTED_TEXT
            frame_vars["solved_result"][0]["q"] = REDACTED_TEXT
        case {"values": {"q": _}}:
            frame_vars["values"]["q"] = REDACTED_TEXT
        case _:
            pass


def _redact_auth_vars(frame_vars: dict[str, Any]) -> None:
    """Redact third-party API credentials out of the frame locals that carry them."""
    args = frame_vars.get("args")
    if isinstance(args, dict) and "key" in args:
        args["key"] = REDACTED_TEXT

    headers = frame_vars.get("headers")
    if isinstance(headers, dict):
        for header in headers:
            if str(header).lower() == "ocp-apim-subscription-key":
                headers[header] = REDACTED_TEXT


def _redact_frame(frame: dict[str, Any]) -> None:
    """Redact sensitive locals out of a single stack frame."""
    frame_vars = frame.get("vars")
    if not isinstance(frame_vars, dict):
        return

    if _is_search_term_frame(frame):
        for name in frame_vars.keys() - EXEMPT_VAR_NAMES:
            frame_vars[name] = REDACTED_TEXT
        return

    _redact_suggest_vars(frame_vars)
    _redact_auth_vars(frame_vars)
    # Third-party frames (httpx, FastAPI, pydantic, Pub/Sub, Elasticsearch) hold the
    # payload under names we cannot enumerate, so match on the content instead.
    for name, value in list(frame_vars.items()):
        if value != REDACTED_TEXT and _contains_payload(value):
            frame_vars[name] = REDACTED_TEXT


def strip_sensitive_data(event: Event, hint: Hint) -> Event | None:
    """Filter out sensitive data from Sentry events.

    A user query reaches an event through more than one channel, so every part of the
    event that can carry one is swept: the request (query string and captured body), the
    frame locals of every exception and thread stacktrace, the exception messages, and the
    log record extras and breadcrumbs.

    Two matching strategies are combined, because neither covers the payload alone.
      - Frames on the search term path (`SEARCH_TERM_MODULES`) are redacted by default.
      - Everywhere else -- third-party frames, request bodies, breadcrumbs -- names cannot be
        enumerated, so values are matched on their content instead, against `SENSITIVE_KEYS`
        for structured data and `PAYLOAD_MARKERS` for anything already serialized to text.

    Runs as Sentry's `before_send` hook, which means it runs after the SDK has serialized
    the event: `event` is an acyclic structure of primitives, and is redacted in place. It
    must not raise -- Sentry swallows the error and drops the whole event -- so missing or
    unexpected keys are tolerated throughout and unserializable values fail closed.

    See: https://docs.sentry.io/platforms/python/configuration/filtering/
    """
    request = event.get("request")
    if isinstance(request, dict):
        if request.get("query_string"):
            request["query_string"] = REDACTED_TEXT
        # Sentry's Starlette integration captures the parsed JSON body, which for the
        # search terms submission endpoint is the whole batch of raw queries.
        _redact_keys(request.get("data"))

    for frame in _iter_frames(event):
        _redact_frame(frame)

    # A pydantic ValidationError embeds the offending input in its message, and every
    # search term model is constructed from user query data.
    for entry in event.get("exception", {}).get("values", []):
        if isinstance(entry, dict) and _contains_payload(entry.get("value")):
            entry["value"] = REDACTED_TEXT

    # Records from a logger that is not in `SEARCH_TERM_LOGGERS` can still carry a query
    # in their `extra`; those land here.
    _redact_keys(event.get("extra"))
    breadcrumbs = event.get("breadcrumbs")
    if isinstance(breadcrumbs, dict):
        for crumb in breadcrumbs.get("values", []):
            _redact_keys(crumb.get("data"))

    return event
