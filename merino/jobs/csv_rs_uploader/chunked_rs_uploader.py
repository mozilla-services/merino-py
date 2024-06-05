"""Chunked remote settings uploader"""
import logging
from typing import Any

import kinto_http

from merino.jobs.utils.chunked_rs_uploader import Chunk, ChunkedRemoteSettingsUploader

logger = logging.getLogger(__name__)


class ChunkedRemoteSettingsSuggestionUploader(ChunkedRemoteSettingsUploader):
    """A class that uploads suggestion data to remote settings."""

    chunk_size: int
    current_chunk: Chunk
    dry_run: bool
    kinto: kinto_http.Client
    record_type: str
    suggestion_score_fallback: float | None
    total_data_count: int | None

    def __init__(
        self,
        auth: str,
        bucket: str,
        chunk_size: int,
        collection: str,
        record_type: str,
        server: str,
        dry_run: bool = False,
        suggestion_score_fallback: float | None = None,
        total_data_count: int | None = None,
    ):
        """Initialize the uploader."""
        super(ChunkedRemoteSettingsSuggestionUploader, self).__init__(
            auth,
            bucket,
            chunk_size,
            collection,
            record_type,
            server,
            dry_run,
            total_data_count,
        )
        self.suggestion_score_fallback = suggestion_score_fallback
        self.total_data_count = total_data_count

    def add_suggestion(self, suggestion: dict[str, Any]) -> None:
        """Add a suggestion. If the current chunk becomes full as a result, it
        will be uploaded before this method returns.
        """
        if self.suggestion_score_fallback and "score" not in suggestion:
            suggestion |= {"score": self.suggestion_score_fallback}
        self.current_chunk.add_data(suggestion)
        if self.current_chunk.size == self.chunk_size:
            self._finish_current_chunk()
