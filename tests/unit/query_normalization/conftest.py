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


@pytest.fixture(autouse=True)
def _load_wordsegment() -> None:
    """Ensure wordsegment tables are loaded for all tests."""
    wordsegment.load()


@pytest.fixture(name="canonical")
def fixture_canonical() -> set[str]:
    """Build canonical set from test data."""
    canonical: set[str] = set()

    # Sports teams
    sports = json.loads((_DATA_DIR / "sports_teams.json").read_text())
    canonical.update(sports)

    # Finance keywords
    fin = json.loads((_DATA_DIR / "finance_tickers.json").read_text())
    canonical.update(fin.get("keyword_to_stock_ticker", {}).keys())
    canonical.update(fin.get("keyword_to_etf_tickers", {}).keys())

    return canonical


@pytest.fixture(name="finance_bm25")
def fixture_finance_bm25() -> BM25Index:
    """Build finance BM25 index from test data."""
    fin = json.loads((_DATA_DIR / "finance_tickers.json").read_text())
    keywords = list(
        {
            *fin.get("keyword_to_stock_ticker", {}).keys(),
            *fin.get("keyword_to_etf_tickers", {}).keys(),
        }
    )
    return BM25Index(keywords)


@pytest.fixture(name="prefix_index")
def fixture_prefix_index() -> dict[str, tuple[str, int, int]]:
    """Build prefix index from test word_freq.csv."""
    vocab: dict[str, int] = {}
    with open(_DATA_DIR / "word_freq.csv") as f:
        reader = csv.DictReader(f)
        for row in reader:
            vocab[row["word"]] = int(row["freq"])
    return build_prefix_index(vocab)


@pytest.fixture(name="pipeline")
def fixture_pipeline(
    canonical: set[str],
    finance_bm25: BM25Index,
    prefix_index: dict[str, tuple[str, int, int]],
) -> NormalizePipeline:
    """Build a NormalizePipeline from test data."""
    return NormalizePipeline(
        canonical=canonical,
        finance_bm25=finance_bm25,
        canonical_prefix_index=prefix_index,
    )
