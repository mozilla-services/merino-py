from logging.config import dictConfig

from merino.config import settings


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
                    "level": settings.logging.level,
                    "class": "logging.StreamHandler",
                    "formatter": settings.logging.format,
                }
            },
            "loggers": {
                "merino": {"handlers": ["console"], "level": settings.logging.level},
                "request.summary": {
                    "handlers": ["console"],
                    "level": settings.logging.level,
                },
                "web.suggest.request": {
                    "handlers": ["console"],
                    "level": settings.logging.level,
                },
            },
        }
    )
