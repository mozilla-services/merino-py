"""Logging configuration"""
from logging.config import dictConfig

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
                    "()": "dockerflow.logging.JsonLogFormatter",
                    "logger_name": "merino",
                },
            },
            "handlers": {
                "console-mozlog": {
                    "level": settings.logging.level,
                    "class": "logging.StreamHandler",
                    "formatter": "json",
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
                },
            },
            "loggers": {
                "merino": {
                    "handlers": handler,
                    "level": settings.logging.level,
                },
                "request.summary": {
                    "handlers": handler,
                    "level": settings.logging.level,
                },
                "web.suggest.request": {
                    "handlers": handler,
                    "level": settings.logging.level,
                },
                "uvicorn.error": {
                    "handlers": ["uvicorn-error-handler"],
                    "level": "ERROR",
                    "propagate": False,
                },
            },
        }
    )
