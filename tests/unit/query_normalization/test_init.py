"""Unit tests for query normalization initialization."""

from unittest.mock import AsyncMock, patch

import pytest

import merino.query_normalization as qn_module
from merino.query_normalization import get_pipeline, init_pipeline


@pytest.fixture(autouse=True)
def _reset_pipeline() -> None:
    """Reset the global pipeline singleton before each test."""
    qn_module._pipeline = None


@pytest.mark.asyncio
async def test_init_pipeline_disabled() -> None:
    """Pipeline should not initialize when disabled."""
    with patch("merino.query_normalization.settings") as mock_settings:
        mock_settings.query_normalization.enabled = False
        await init_pipeline()
        assert get_pipeline() is None


@pytest.mark.asyncio
async def test_init_pipeline_local() -> None:
    """Pipeline should initialize with local filemanager."""
    with patch("merino.query_normalization.settings") as mock_settings:
        mock_settings.query_normalization.enabled = True
        mock_settings.query_normalization.data_source = "local"
        mock_settings.query_normalization.sports_teams_file = (
            "tests/data/query_normalization/sports_teams.json"
        )
        mock_settings.query_normalization.word_freq_file = (
            "tests/data/query_normalization/word_freq.csv"
        )
        mock_settings.query_normalization.finance_tickers_file = (
            "tests/data/query_normalization/finance_tickers.json"
        )
        await init_pipeline()
        pipeline = get_pipeline()
        assert pipeline is not None
        assert pipeline.normalize("dow jone") == "dow jones"


@pytest.mark.asyncio
async def test_init_pipeline_remote() -> None:
    """Pipeline should initialize with remote filemanager."""
    with (
        patch("merino.query_normalization.settings") as mock_settings,
        patch("merino.query_normalization.QueryNormRemoteFileManager") as mock_remote_cls,
    ):
        mock_settings.query_normalization.enabled = True
        mock_settings.query_normalization.data_source = "remote"
        mock_settings.query_normalization.gcs_bucket = "test-bucket"

        mock_fm = AsyncMock()
        mock_fm.get_sports_teams.return_value = {"lakers", "bulls"}
        mock_fm.get_word_freq.return_value = {"weather": 465297, "stock": 193730}
        mock_fm.get_finance_keywords.return_value = ["apple stock", "dow jones"]
        mock_remote_cls.return_value = mock_fm

        await init_pipeline()
        pipeline = get_pipeline()
        assert pipeline is not None
