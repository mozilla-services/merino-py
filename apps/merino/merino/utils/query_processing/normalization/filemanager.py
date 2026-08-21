"""Filemanagers for loading query normalization data from local files or GCS."""

import csv
import json
import logging
from enum import Enum
from pathlib import Path
from typing import Any, Protocol

from gcloud.aio.storage import Blob, Bucket, Storage

logger = logging.getLogger(__name__)


class QueryNormDataSource(str, Enum):
    """Source enum for normalization data."""

    REMOTE = "remote"
    LOCAL = "local"


class QueryNormFileManager(Protocol):
    """Protocol for normalization data loading."""

    async def get_sports_teams(self) -> set[str]:
        """Return set of sports team names."""
        ...  # pragma: no cover

    async def get_word_freq(self) -> dict[str, int]:
        """Return word frequency dict for prefix completion."""
        ...  # pragma: no cover

    async def get_finance_keywords(self) -> list[str]:
        """Return list of finance keywords for BM25 index."""
        ...  # pragma: no cover


class QueryNormLocalFileManager:
    """Load normalization data from local files."""

    def __init__(
        self,
        sports_teams_path: str,
        word_freq_path: str,
        finance_tickers_path: str,
    ) -> None:
        """Initialize with local file paths."""
        self._sports_path = Path(sports_teams_path)
        self._word_freq_path = Path(word_freq_path)
        self._finance_path = Path(finance_tickers_path)

    async def get_sports_teams(self) -> set[str]:
        """Load sports team names from local JSON file."""
        data = json.loads(self._sports_path.read_text())
        logger.info(f"Loaded {len(data)} sports teams from {self._sports_path}")
        return set(data)

    async def get_word_freq(self) -> dict[str, int]:
        """Load word frequencies from local CSV file."""
        vocab: dict[str, int] = {}
        with open(self._word_freq_path) as f:
            reader = csv.DictReader(f)
            for row in reader:
                vocab[row["word"]] = int(row["freq"])
        logger.info(f"Loaded {len(vocab)} words from {self._word_freq_path}")
        return vocab

    async def get_finance_keywords(self) -> list[str]:
        """Load finance keywords from local JSON file."""
        data = json.loads(self._finance_path.read_text())
        keywords = list(
            {
                *data.get("keyword_to_stock_ticker", {}).keys(),
                *data.get("keyword_to_etf_tickers", {}).keys(),
            }
        )
        logger.info(f"Loaded {len(keywords)} finance keywords from {self._finance_path}")
        return keywords


class QueryNormRemoteFileManager:
    """Load normalization data from GCS."""

    def __init__(self, gcs_bucket_path: str) -> None:
        """Initialize with GCS bucket path."""
        self._gcs_bucket_path = gcs_bucket_path
        self._gcs_client: Storage | None = None
        self._bucket: Bucket | None = None

    async def _get_bucket(self) -> Bucket:
        """Lazily instantiate the GCS client and return the bucket."""
        if self._bucket is not None:
            return self._bucket
        if self._gcs_client is None:
            self._gcs_client = Storage()
        self._bucket = Bucket(storage=self._gcs_client, name=self._gcs_bucket_path)
        return self._bucket

    async def _fetch_json(self, blob_name: str) -> Any:
        """Fetch and parse a JSON blob from GCS."""
        bucket = await self._get_bucket()
        blob: Blob = await bucket.get_blob(blob_name)
        blob_data = await blob.download()
        return json.loads(blob_data)

    async def _fetch_csv(self, blob_name: str) -> dict[str, int]:
        """Fetch a CSV blob from GCS and parse as word->freq dict."""
        bucket = await self._get_bucket()
        blob: Blob = await bucket.get_blob(blob_name)
        blob_data = await blob.download()
        text = blob_data.decode("utf-8") if isinstance(blob_data, bytes) else blob_data
        vocab: dict[str, int] = {}
        for line in text.strip().split("\n")[1:]:  # skip header
            word, freq = line.split(",", 1)
            vocab[word] = int(freq)
        return vocab

    async def get_sports_teams(self) -> set[str]:
        """Fetch sports team names from GCS."""
        data = await self._fetch_json("query_normalization/sports_teams.json")
        logger.info(f"Loaded {len(data)} sports teams from GCS")
        return set(data)

    async def get_word_freq(self) -> dict[str, int]:
        """Fetch word frequencies from GCS."""
        vocab = await self._fetch_csv("query_normalization/word_freq.csv")
        logger.info(f"Loaded {len(vocab)} words from GCS")
        return vocab

    async def get_finance_keywords(self) -> list[str]:
        """Fetch finance keywords from GCS."""
        data = await self._fetch_json("query_normalization/finance_tickers.json")
        keywords = list(
            {
                *data.get("keyword_to_stock_ticker", {}).keys(),
                *data.get("keyword_to_etf_tickers", {}).keys(),
            }
        )
        logger.info(f"Loaded {len(keywords)} finance keywords from GCS")
        return keywords
