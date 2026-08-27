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


def test_is_person_batch_preserves_input_order(detector: PiiDetector) -> None:
    """Batch verdicts line up positionally with the input texts.

    Callers map verdicts back onto their inputs by index, so a reordering bug would
    silently mislabel unrelated search terms. The PERSON hits sit at interior,
    non-symmetric positions so an off-by-one or reversal cannot pass.
    """
    texts = [
        "The weather is nice today.",
        "Barack Obama visited Berlin.",
        "best pizza recipe",
        "Ada Lovelace wrote the first algorithm.",
        "how tall is the eiffel tower",
    ]

    assert detector.is_person_batch(texts) == [False, True, False, True, False]


def test_is_person_batch_agrees_with_is_person(detector: PiiDetector) -> None:
    """Batched and single-text detection reach the same verdict for the same text."""
    for text in ("Barack Obama visited Berlin.", "The weather is nice today."):
        assert detector.is_person_batch([text]) == [detector.is_person(text)]


def test_is_person_batch_empty(detector: PiiDetector) -> None:
    """An empty batch returns no verdicts without invoking the pipeline.

    SpaCy rejects `batch_size=0`, so the empty case must short-circuit rather than
    reach `nlp.pipe`.
    """
    assert detector.is_person_batch([]) == []


def test_detection_does_not_grow_the_vocab(detector: PiiDetector) -> None:
    """Detecting over novel tokens leaves the shared StringStore unchanged.

    SpaCy interns every unseen token into the `Vocab` permanently, so without the
    memory zone this long-lived process leaks for every novel search term it reads.
    The tokens below are nonsense precisely so none of them can already be interned.
    """
    before = len(detector.nlp.vocab.strings)

    detector.is_person_batch([f"zqxjw{n:04d}kbrf mplvth{n:04d}" for n in range(200)])
    detector.is_person("gwyndal thraxine plovemsk")

    assert len(detector.nlp.vocab.strings) == before


def test_recycle_replaces_the_pipeline_once_the_threshold_is_reached() -> None:
    """The pipeline is reloaded only after `recycle_after_texts` texts have passed.

    Recycling is what bounds the index capacity a memory zone cannot reclaim, so a
    threshold that never fires -- or fires on every batch -- would either leak or pay
    a model reload per request.
    """
    detector = PiiDetector(
        model_name="en_core_web_sm", excluded_components=EXCLUDED, recycle_after_texts=10
    )
    first = detector.nlp

    detector.is_person_batch(["a query", "another query"])
    assert detector.nlp is first, "recycled before reaching the threshold"

    # 2 + 7 = 9 texts, still one short.
    detector.is_person_batch(["filler"] * 7)
    assert detector.nlp is first, "recycled one text early"

    detector.is_person("the tenth text")
    assert detector.nlp is not first, "did not recycle on reaching the threshold"
    assert detector._texts_since_load == 0


def test_recycle_disabled_by_default(detector: PiiDetector) -> None:
    """A zero threshold keeps the originally loaded pipeline forever."""
    original = detector.nlp
    detector.is_person_batch(["some query"] * 50)
    assert detector.nlp is original


def test_recycled_detector_still_detects() -> None:
    """Detection works across a recycle, on both the old and the replacement pipeline."""
    detector = PiiDetector(
        model_name="en_core_web_sm", excluded_components=EXCLUDED, recycle_after_texts=1
    )
    for _ in range(3):
        assert detector.is_person("Barack Obama visited Berlin.") is True
        assert detector.is_person_batch(["The weather is nice today."]) == [False]
