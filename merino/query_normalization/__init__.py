"""Query normalization pipeline initialization and access."""

import logging

from merino.configs import settings
from merino.query_normalization.filemanager import (
    QueryNormDataSource,
    QueryNormFileManager,
    QueryNormLocalFileManager,
    QueryNormRemoteFileManager,
)
from merino.query_normalization.pipeline import (
    BM25Index,
    NormalizePipeline,
    build_prefix_index,
)

logger = logging.getLogger(__name__)

_pipeline: NormalizePipeline | None = None


async def init_pipeline() -> None:
    """Initialize the normalization pipeline from config.

    Should only be called once at startup.
    """
    global _pipeline

    if not settings.query_normalization.enabled:
        logger.info("Query normalization is disabled")
        return

    data_source = settings.query_normalization.data_source

    filemanager: QueryNormFileManager
    if data_source == QueryNormDataSource.REMOTE:
        filemanager = QueryNormRemoteFileManager(
            gcs_bucket_path=settings.query_normalization.gcs_bucket,
        )
    else:
        filemanager = QueryNormLocalFileManager(
            sports_teams_path=settings.query_normalization.sports_teams_file,
            word_freq_path=settings.query_normalization.word_freq_file,
            finance_tickers_path=settings.query_normalization.finance_tickers_file,
        )

    sports_teams = await filemanager.get_sports_teams()
    word_freq = await filemanager.get_word_freq()
    finance_keywords = await filemanager.get_finance_keywords()

    canonical: set[str] = set()
    canonical.update(sports_teams)
    canonical.update(finance_keywords)

    finance_bm25 = BM25Index(finance_keywords)
    prefix_index = build_prefix_index(word_freq)

    _pipeline = NormalizePipeline(
        canonical=canonical,
        finance_bm25=finance_bm25,
        canonical_prefix_index=prefix_index,
    )

    logger.info(
        "Query normalization pipeline initialized",
        extra={
            "canonical_terms": len(canonical),
            "finance_keywords": len(finance_keywords),
            "sports_teams": len(sports_teams),
            "prefix_words": len(word_freq),
        },
    )


def get_pipeline() -> NormalizePipeline | None:
    """Return the normalization pipeline, or None if disabled."""
    return _pipeline
