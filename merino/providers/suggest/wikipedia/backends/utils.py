"""Utilities for the Wikipedia backend."""

from merino.configs import settings

SUPPORTED_LANGUAGES: frozenset = frozenset(settings.suggest_supported_languages)


def get_language_code(requested_languages: list[str]) -> str:
    """Return the first supported base language code from the input list, or fall back to 'en'."""
    for lang in requested_languages:
        base = lang.lower().split("-")[0]
        if base in SUPPORTED_LANGUAGES:
            return base
    return "en"
