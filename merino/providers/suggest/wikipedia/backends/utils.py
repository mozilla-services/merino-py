"""Utilities for the Wikipedia backend."""

from merino.configs import settings

SUPPORTED_LANGUAGES = frozenset = frozenset(settings.suggest_supported_languages)

def get_language_code(requested_languages: list[str]) -> str:
    """Get first language code that is in supported_languages."""
    language = next(
        (language for language in requested_languages if language in SUPPORTED_LANGUAGES), "en-US"
    )

    return language.lower().split("-")[0]


