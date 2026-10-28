"""Unit tests for the wikipedia article blocklist generator."""

import json
from datetime import datetime

import pytest

from merino.jobs.wikipedia_article_blocklist.generator import ArticleBlocklistGenerator
from merino.jobs.wikipedia_indexer.filemanager import Snapshot

SNAPSHOT = Snapshot(
    name="enwiki-20260816-cirrussearch-content",
    date=datetime(2026, 8, 16),
    prefix="prefix/enwiki-20260816-cirrussearch-content",
)


def _export(*docs: dict) -> list[bytes]:
    """Build the export lines, an operator line followed by each document."""
    lines = []
    for i, doc in enumerate(docs):
        lines.append(json.dumps({"index": {"_id": str(i)}}).encode())
        lines.append(json.dumps(doc).encode())
    return lines


@pytest.fixture(name="file_manager")
def fixture_file_manager(mocker):
    """Return a FileManager mock serving the latest snapshot."""
    file_manager = mocker.MagicMock()
    file_manager.language = "en"
    file_manager.get_latest_gcs.return_value = SNAPSHOT
    return file_manager


def test_generate_writes_blocked_articles(file_manager):
    """Verify only articles in a blocked category are written, with their QID."""
    file_manager.stream_from_gcs.return_value = iter(
        _export(
            {"title": "Blocked", "category": ["Bad", "Other"], "wikibase_item": "Q1"},
            {"title": "Allowed", "category": ["Other"], "wikibase_item": "Q2"},
            {"title": "No QID", "category": ["Bad"]},
            {"title": "Redirect", "category": ["Bad"], "page_type": "redirect"},
            {"title": "No categories", "wikibase_item": "Q3"},
        )
    )

    result = ArticleBlocklistGenerator({"Bad"}, file_manager).generate(5)

    assert result.splitlines() == ["title,qid", "Blocked,Q1", "No QID,"]
    file_manager.stream_from_gcs.assert_called_once_with(SNAPSHOT)


def test_generate_quotes_titles_with_commas(file_manager):
    """Verify titles containing commas stay in a single CSV column."""
    file_manager.stream_from_gcs.return_value = iter(
        _export({"title": "Paris, France", "category": ["Bad"], "wikibase_item": "Q90"})
    )

    result = ArticleBlocklistGenerator({"Bad"}, file_manager).generate(1)

    assert result.splitlines() == ["title,qid", '"Paris, France",Q90']


def test_generate_raises_when_nothing_is_blocked(file_manager):
    """Verify an error is raised rather than returning an empty blocklist."""
    file_manager.stream_from_gcs.return_value = iter(
        _export({"title": "Allowed", "category": ["Other"], "wikibase_item": "Q2"})
    )

    with pytest.raises(RuntimeError, match="No articles matched the category blocklist"):
        ArticleBlocklistGenerator({"Bad"}, file_manager).generate(1)


def test_generate_raises_without_export(file_manager):
    """Verify an error is raised when no export is available on GCS."""
    file_manager.get_latest_gcs.return_value = None

    with pytest.raises(RuntimeError, match="No exports available on GCS for en"):
        ArticleBlocklistGenerator({"Bad"}, file_manager).generate(1)
