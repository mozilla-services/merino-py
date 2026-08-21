# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the config_logging.py module."""

import logging
from typing import Any

import pytest

from merino_common.app_configs.config_logging import configure_logging


@pytest.fixture(autouse=True)
def restore_logger_disabled_state() -> Any:
    """Restore each logger's ``disabled`` flag after the test.

    ``configure_logging`` calls ``logging.config.dictConfig``, which defaults to
    ``disable_existing_loggers=True``. Without this fixture, configuring logging here
    silently disables loggers created elsewhere during collection and breaks unrelated
    tests that rely on caplog. The config names ``merino_common``, so the shared modules
    are safe; anything outside the configured namespaces (third-party loggers, test
    modules) is not.
    """
    logger_dict = logging.root.manager.loggerDict
    snapshot = {
        name: logger.disabled
        for name, logger in logger_dict.items()
        if isinstance(logger, logging.Logger)
    }
    yield
    for name, disabled in snapshot.items():
        logger = logger_dict.get(name)
        if isinstance(logger, logging.Logger):
            logger.disabled = disabled


def test_configure_logging_invalid_format() -> None:
    """configure_logging raises ValueError when given an unknown log format."""
    with pytest.raises(ValueError, match="Invalid log format"):
        configure_logging(
            log_format="invalid",
            level="INFO",
            can_propagate=False,
            current_env="development",
            logger_name="merino",
        )


def test_configure_logging_mozlog_production() -> None:
    """configure_logging raises ValueError if production runs with a non-mozlog format."""
    with pytest.raises(ValueError, match="Log format must be 'mozlog' in production"):
        configure_logging(
            log_format="pretty",
            level="INFO",
            can_propagate=False,
            current_env="production",
            logger_name="merino",
        )


@pytest.mark.parametrize(
    ("log_format", "expected_handler"),
    [("mozlog", "console-mozlog"), ("pretty", "console-pretty")],
    ids=["mozlog", "pretty"],
)
def test_configure_log_handler_assigned(log_format: str, expected_handler: str) -> None:
    """The configured logger uses the handler matching the requested log_format."""
    configure_logging(
        log_format=log_format,
        level="INFO",
        can_propagate=False,
        current_env="development",
        logger_name="merino",
    )

    log_manager: Any = logging.root.manager
    handler_name: Any = log_manager.loggerDict["merino"].handlers[0].name
    assert handler_name == expected_handler


@pytest.mark.parametrize("logger_name", ["merino", "merino_fleece"], ids=["merino", "fleece"])
@pytest.mark.parametrize(
    "shared_logger",
    [
        "merino_common.utils.cron",
        "merino_common.utils.async_batch_queue",
        "merino_common.routers.dockerflow",
        "merino_common.app_configs.config_sentry",
    ],
)
def test_shared_loggers_survive_configuration(shared_logger: str, logger_name: str) -> None:
    """A `merino_common.*` logger created before configuration is not disabled by it.

    `merino_common` is a sibling namespace of both apps' `logger_name`, and every shared
    module binds its logger at import time -- which happens before the app lifespan calls
    this function. `dictConfig` disables pre-existing loggers it is not told about, so
    without a `merino_common` entry these all go silent in production while still passing
    every test that does not configure logging.
    """
    logging.getLogger(shared_logger)

    configure_logging(
        log_format="mozlog",
        level="INFO",
        can_propagate=False,
        current_env="development",
        logger_name=logger_name,
    )

    assert logging.getLogger(shared_logger).disabled is False
    assert logging.getLogger(shared_logger).isEnabledFor(logging.INFO)


def test_shared_logger_records_reach_the_configured_handler() -> None:
    """A record emitted by a shared module lands on the app's own log handler.

    Guards the routing as well as the `disabled` flag: being enabled is worthless if the
    record has no handler to reach.
    """
    cron_logger = logging.getLogger("merino_common.utils.cron")

    configure_logging(
        log_format="mozlog",
        level="INFO",
        can_propagate=False,
        current_env="development",
        logger_name="merino_fleece",
    )

    records: list[logging.LogRecord] = []

    class Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    parent = logging.getLogger("merino_common")
    assert parent.handlers[0].name == "console-mozlog", "shared loggers must route to MozLog"
    capture = Capture()
    parent.addHandler(capture)
    try:
        cron_logger.info("Cron: successfully ran task refresh_amp")
    finally:
        parent.removeHandler(capture)

    assert [record.getMessage() for record in records] == [
        "Cron: successfully ran task refresh_amp"
    ]


def test_configure_logging_uses_provided_logger_name() -> None:
    """The logger named by `logger_name` is configured (not a hardcoded "merino")."""
    configure_logging(
        log_format="mozlog",
        level="INFO",
        can_propagate=False,
        current_env="development",
        logger_name="merino_fleece",
    )

    log_manager: Any = logging.root.manager
    assert "merino_fleece" in log_manager.loggerDict
    assert log_manager.loggerDict["merino_fleece"].handlers[0].name == "console-mozlog"
