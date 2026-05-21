"""Fixtures for query normalization tests."""

import csv
import json
from pathlib import Path

import pytest
import wordsegment

from merino.utils.query_processing.normalization.pipeline import (
    BM25Index,
    NormalizePipeline,
    build_prefix_index,
)

_DATA_DIR = Path(__file__).parent.parent.parent / "data" / "query_normalization"


@pytest.fixture(scope="session", autouse=True)
def _load_wordsegment() -> None:
    """Load wordsegment once; stub reloads since load() re-parses ~10MB each call."""
    wordsegment.load()
    wordsegment.load = lambda: None  # type: ignore[assignment]
    wordsegment._segmenter.load = lambda: None  # type: ignore[assignment]


@pytest.fixture(scope="session", name="_canonical_base")
def fixture_canonical_base() -> set[str]:
    """Load the canonical set once per session. Treat as read-only."""
    base: set[str] = set()
    sports = json.loads((_DATA_DIR / "sports_teams.json").read_text())
    base.update(sports)
    fin = json.loads((_DATA_DIR / "finance_tickers.json").read_text())
    base.update(fin.get("keyword_to_stock_ticker", {}).keys())
    base.update(fin.get("keyword_to_etf_tickers", {}).keys())
    return base


@pytest.fixture(name="canonical")
def fixture_canonical(_canonical_base: set[str]) -> set[str]:
    """Return a fresh per-test copy of the canonical set (some tests mutate it)."""
    return set(_canonical_base)


@pytest.fixture(scope="session", name="finance_bm25")
def fixture_finance_bm25() -> BM25Index:
    """Build finance BM25 index once per session."""
    fin = json.loads((_DATA_DIR / "finance_tickers.json").read_text())
    keywords = list(
        {
            *fin.get("keyword_to_stock_ticker", {}).keys(),
            *fin.get("keyword_to_etf_tickers", {}).keys(),
        }
    )
    return BM25Index(keywords)


@pytest.fixture(scope="session", name="prefix_index")
def fixture_prefix_index() -> dict[str, tuple[str, int, int]]:
    """Build prefix index once per session."""
    vocab: dict[str, int] = {}
    with open(_DATA_DIR / "word_freq.csv") as f:
        reader = csv.DictReader(f)
        for row in reader:
            vocab[row["word"]] = int(row["freq"])
    return build_prefix_index(vocab)


@pytest.fixture(scope="session", name="pipeline")
def fixture_pipeline(
    _canonical_base: set[str],
    finance_bm25: BM25Index,
    prefix_index: dict[str, tuple[str, int, int]],
) -> NormalizePipeline:
    """Build a NormalizePipeline once per session."""
    return NormalizePipeline(
        canonical=set(_canonical_base),
        finance_bm25=finance_bm25,
        canonical_prefix_index=prefix_index,
    )
