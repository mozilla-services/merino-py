"""Unit tests for query normalization filemanagers."""

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from merino.utils.query_processing.normalization.filemanager import (
    QueryNormLocalFileManager,
    QueryNormRemoteFileManager,
)

_DATA_DIR = Path(__file__).parent.parent.parent / "data" / "query_normalization"


# Local filemanager tests
@pytest.fixture(name="local_fm")
def fixture_local_fm() -> QueryNormLocalFileManager:
    """Create a local filemanager pointing at test data."""
    return QueryNormLocalFileManager(
        sports_teams_path=str(_DATA_DIR / "sports_teams.json"),
        word_freq_path=str(_DATA_DIR / "word_freq.csv"),
        finance_tickers_path=str(_DATA_DIR / "finance_tickers.json"),
    )


@pytest.mark.asyncio
async def test_local_get_sports_teams(local_fm: QueryNormLocalFileManager) -> None:
    """Load sports teams from local test data."""
    teams = await local_fm.get_sports_teams()
    assert isinstance(teams, set)
    assert "lakers" in teams
    assert "red sox" in teams
    assert len(teams) > 0


@pytest.mark.asyncio
async def test_local_get_word_freq(local_fm: QueryNormLocalFileManager) -> None:
    """Load word frequencies from local test data."""
    vocab = await local_fm.get_word_freq()
    assert isinstance(vocab, dict)
    assert "weather" in vocab
    assert vocab["weather"] == 465297
    assert len(vocab) > 0


@pytest.mark.asyncio
async def test_local_get_finance_keywords(local_fm: QueryNormLocalFileManager) -> None:
    """Load finance keywords from local test data."""
    keywords = await local_fm.get_finance_keywords()
    assert isinstance(keywords, list)
    assert "dow jones" in keywords
    assert len(keywords) > 0


# Remote filemanager tests
def _mock_blob(data: bytes) -> AsyncMock:
    """Create a mock GCS blob that returns the given data."""
    blob = AsyncMock()
    blob.download.return_value = data
    return blob


@pytest.fixture(name="mock_bucket")
def fixture_mock_bucket() -> AsyncMock:
    """Create a mock GCS bucket."""
    return AsyncMock()


@pytest.fixture(name="remote_fm")
def fixture_remote_fm(mock_bucket: AsyncMock) -> QueryNormRemoteFileManager:
    """Create a remote filemanager with mocked GCS bucket."""
    fm = QueryNormRemoteFileManager(gcs_bucket_path="test-bucket")
    fm._bucket = mock_bucket
    return fm


@pytest.mark.asyncio
async def test_remote_get_sports_teams(
    remote_fm: QueryNormRemoteFileManager, mock_bucket: AsyncMock
) -> None:
    """Fetch sports teams from mocked GCS."""
    teams_data = json.dumps(["lakers", "bulls", "red sox"]).encode()
    mock_bucket.get_blob.return_value = _mock_blob(teams_data)

    teams = await remote_fm.get_sports_teams()
    assert teams == {"lakers", "bulls", "red sox"}
    mock_bucket.get_blob.assert_called_with("query_normalization/sports_teams.json")


@pytest.mark.asyncio
async def test_remote_get_word_freq(
    remote_fm: QueryNormRemoteFileManager, mock_bucket: AsyncMock
) -> None:
    """Fetch word frequencies from mocked GCS."""
    csv_data = b"word,freq\nweather,465297\nstock,193730"
    mock_bucket.get_blob.return_value = _mock_blob(csv_data)

    vocab = await remote_fm.get_word_freq()
    assert vocab == {"weather": 465297, "stock": 193730}
    mock_bucket.get_blob.assert_called_with("query_normalization/word_freq.csv")


@pytest.mark.asyncio
async def test_remote_get_finance_keywords(
    remote_fm: QueryNormRemoteFileManager, mock_bucket: AsyncMock
) -> None:
    """Fetch finance keywords from mocked GCS."""
    fin_data = json.dumps(
        {
            "keyword_to_stock_ticker": {"apple stock": "AAPL"},
            "keyword_to_etf_tickers": {"dow jones": ["DIA"]},
        }
    ).encode()
    mock_bucket.get_blob.return_value = _mock_blob(fin_data)

    keywords = await remote_fm.get_finance_keywords()
    assert "apple stock" in keywords
    assert "dow jones" in keywords
    mock_bucket.get_blob.assert_called_with("query_normalization/finance_tickers.json")
