"""Unit tests for section parsing helpers in sections_backend.py."""

import pytest

from merino.curated_recommendations.corpus_backends.sections_backend import (
    parse_section_external_id,
)


class TestParseSectionExternalId:
    """Tests covering raw section ID normalization."""

    @pytest.mark.parametrize(
        ("raw_external_id", "expected"),
        [
            ("government", ("government", 0)),
            ("government__lDE_DE", ("government", 0)),
            ("government__other", ("government", 0)),
            ("government__exp5050", ("government", 5050)),
            ("government__exp5050__lDE_DE", ("government", 5050)),
            ("government__exp", ("government", 0)),
            ("government__expabc", ("government", 0)),
            ("government__exp5050_variant", ("government", 0)),
            ("__exp5050__lDE_DE", ("", 0)),
        ],
    )
    def test_parse_section_external_id(self, raw_external_id: str, expected: tuple[str, int]):
        """Parser should strip locale suffixes and drop malformed experiment variants."""
        assert parse_section_external_id(raw_external_id) == expected
