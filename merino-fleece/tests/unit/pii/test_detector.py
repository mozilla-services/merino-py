"""Unit tests for merino_fleece.pii.detector."""

import pytest

from merino_fleece.pii.detector import PiiDetector

EXCLUDED = ["tok2vec", "tagger", "parser", "attribute_ruler", "lemmatizer"]


@pytest.fixture(scope="module")
def detector() -> PiiDetector:
    """Load the small SpaCy model once per module (auto-downloads on first run)."""
    return PiiDetector(model_name="en_core_web_sm", excluded_components=EXCLUDED)


def test_detects_person(detector: PiiDetector) -> None:
    """Text containing a PERSON entity is flagged as PII."""
    assert detector.is_person("Barack Obama visited Berlin.") is True


def test_no_person(detector: PiiDetector) -> None:
    """Text without a PERSON entity is not flagged."""
    assert detector.is_person("The weather is nice today.") is False
