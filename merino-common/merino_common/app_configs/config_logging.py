"""Logging configuration"""

import logging
import sys
from logging.config import dictConfig

from dockerflow import logging as dockerflow_logging


def configure_logging(
    log_format: str,
    level: str,
    can_propagate: bool,
    current_env: str,
    logger_name: str,
) -> None:
    """Configure logging with MozLog.

    Args:
        log_format: Either "mozlog" or "pretty".
        level: Standard logging level name ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL").
        can_propagate: Whether the application's loggers should propagate to the root logger.
        current_env: The active Dynaconf environment name (e.g. "development", "testing", "stage",
            "production"). Used to enforce that production runs with "mozlog".
        logger_name: Root logger name to configure (e.g. "merino", "merino_fleece"). Also used as
            the MozLog ``Logger`` field on emitted records.
    """
    match log_format:
        case "mozlog":
            handler = ["console-mozlog"]
        case "pretty":
            handler = ["console-pretty"]
        case _:
            raise ValueError(
                f"Invalid log format: {log_format}. Should either be 'mozlog' or 'pretty'."
            )

    if current_env.lower() == "production" and handler != ["console-mozlog"]:
        raise ValueError("Log format must be 'mozlog' in production")

    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "text": {
                    "format": "%(message)s",
                },
                "json": {
                    "()": GCPCompatibleJSONFormatter,
                    "logger_name": logger_name,
                },
            },
            "handlers": {
                "console-mozlog": {
                    "level": level,
                    "class": "logging.StreamHandler",
                    "formatter": "json",
                    "stream": sys.stdout,
                },
                "console-pretty": {
                    "level": level,
                    "class": "rich.logging.RichHandler",
                    "formatter": "json",
                },
                "uvicorn-error-handler": {
                    "level": "ERROR",
                    "class": "logging.StreamHandler",
                    "formatter": "text",
                    "stream": sys.stderr,
                },
            },
            "loggers": {
                logger_name: {
                    "handlers": handler,
                    "level": level,
                    "propagate": can_propagate,
                },
                "web.suggest.request": {
                    "handlers": handler,
                    "level": level,
                    "propagate": can_propagate,
                },
                "uvicorn.error": {
                    "handlers": ["uvicorn-error-handler"],
                    "level": "ERROR",
                    "propagate": False,
                },
            },
        }
    )


class GCPCompatibleJSONFormatter(dockerflow_logging.MozlogFormatter):
    """Override the dockerflow log formatter with GCP compatible levels."""

    STACKDRIVER_LEVEL_MAP = {
        logging.CRITICAL: 600,
        logging.ERROR: 500,
        logging.WARNING: 400,
        logging.INFO: 200,
        logging.DEBUG: 100,
        logging.NOTSET: 0,
    }

    def convert_record(self, record):
        """Overwrite this method to write to the `severity` that is picked up by GCP."""
        out = super().convert_record(record)
        # GCP uses "severity", not "Severity", which is outputted by Mozlog.
        out["severity"] = self.STACKDRIVER_LEVEL_MAP.get(record.levelno, 0)
        return out
