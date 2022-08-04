from logging.config import dictConfig
from os import environ

log_level: str = environ.get("LOG_LEVEL", "INFO").upper()
# TODO: Add another formatter for development
log_format: str = "json"


def configure_logging() -> None:  # pragma: no cover
    """
    Configures logging with MozLog.
    """

    dictConfig(
        {
            "version": 1,
            "formatters": {
                "json": {
                    "()": "dockerflow.logging.JsonLogFormatter",
                    "logger_name": "merino",
                },
            },
            "handlers": {
                "console": {
                    "level": log_level,
                    "class": "logging.StreamHandler",
                    "formatter": log_format,
                }
            },
            "loggers": {
                "merino": {"handlers": ["console"], "level": log_level},
                "request.summary": {"handlers": ["console"], "level": log_level},
            },
        }
    )
