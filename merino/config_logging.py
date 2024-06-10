"""Logging configuration"""

import logging
import sys
from logging.config import dictConfig

from dockerflow import logging as dockerflow_logging

from merino.config import settings


def configure_logging() -> None:
    """Configure logging with MozLog."""
    match settings.logging.format:
        case "mozlog":
            handler = ["console-mozlog"]
        case "pretty":
            handler = ["console-pretty"]
        case _:
            raise ValueError(
                f"Invalid log format: {settings.logging.format}."
                f" Should either be 'mozlog' or 'pretty'."
            )

    if settings.current_env.lower() == "production" and handler != ["console-mozlog"]:
        raise ValueError("Log format must be 'mozlog' in production")

    dictConfig(
        {
            "version": 1,
            "formatters": {
                "text": {
                    "format": "%(message)s",
                },
                "json": {
                    "()": GCPCompatibleJSONFormatter,
                    "logger_name": "merino",
                },
            },
            "handlers": {
                "console-mozlog": {
                    "level": settings.logging.level,
                    "class": "logging.StreamHandler",
                    "formatter": "json",
                    "stream": sys.stdout,
                },
                "console-pretty": {
                    "level": settings.logging.level,
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
                "merino": {
                    "handlers": handler,
                    "level": settings.logging.level,
                    "propagate": settings.logging.can_propagate,
                },
                "request.summary": {
                    "handlers": handler,
                    "level": settings.logging.level,
                    "propagate": settings.logging.can_propagate,
                },
                "web.suggest.request": {
                    "handlers": handler,
                    "level": settings.logging.level,
                    "propagate": settings.logging.can_propagate,
                },
                "uvicorn.error": {
                    "handlers": ["uvicorn-error-handler"],
                    "level": "ERROR",
                    "propagate": False,
                },
            },
        }
    )


class GCPCompatibleJSONFormatter(dockerflow_logging.JsonLogFormatter):
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
