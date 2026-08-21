"""Unit tests for the Wiki Backend Utilities."""

import pytest
from merino.providers.suggest.wikipedia.backends.utils import get_language_code


@pytest.mark.parametrize(
    "input_languages,expected",
    [
        (["en-US"], "en"),
        (["fr-FR"], "fr"),
        (["de"], "de"),
        (["it-IT"], "it"),
        (["pl-PL"], "pl"),
        ([], "en"),
        (["es", "jp", "nl"], "en"),
    ],
)
def test_get_language_code(input_languages, expected):
    """Test that we return the correct language code based on the supported languages"""
    assert get_language_code(input_languages) == expected
