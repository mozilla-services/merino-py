"""The search term sanitization pass, shared by every ingestion path.

Two paths feed this module: the ``/api/v1/search-terms`` endpoint, which buffers terms in an
``AsyncBatchQueue`` and hands over a batch at a time, and the Pub/Sub backup-channel worker,
which hands over one message's search terms at a time. Both must classify and log terms
identically, so the whole pass lives here rather than in either caller.
"""

import logging
from collections import Counter

from merino_common.models.suggest_logging import SuggestRequestParams
from merino_common.utils.query_processing.pii_detect import PIIType, basic_detect
from opentelemetry import metrics

from merino_fleece.configs import settings
from merino_fleece.pii import detect_person_batch, get_detector, get_executor
from merino_fleece.sanitize import exempts
from merino_fleece.utils.log_data_creator import create_search_term_log

# Whether to log `web.suggest.sanitized`.
LOG_SEARCH_TERMS: bool = settings.sanitize.log_search_terms

logger = logging.getLogger(__name__)

# web.suggest.sanitized is used for search terms that sanitization clears as NON_PII.
sanitized_term_logger = logging.getLogger("web.suggest.sanitized")

_meter = metrics.get_meter("fleece")
_sanitize_counter = _meter.create_counter(
    name="search_terms.sanitize",
    unit="{item}",
    description="Number of search terms sanitized, labeled by the detected PII type.",
)


async def sanitize_batch(batch: list[SuggestRequestParams]) -> None:
    """Classify the PII type of every search term in the batch and record it in metrics.

    Queries covered by a registered sanitization exempt short-circuit to
    ``NON_PII`` before any detection runs. Of the rest, cheap pattern matching runs
    over every query first; only the queries it clears reach SpaCy NER, which is
    batched via ``detect_person_batch``. The NER pass is chunked so the shared thread
    pool is released between chunks and concurrent `/pii` requests are not stuck
    behind one long batch.

    Queries are detected over as submitted; bounding their length is the submitter's
    responsibility (Merino prefilters empty and overlong queries before submitting).

    Exceptions are left to propagate, and the callers handle them differently:
    ``AsyncBatchQueue`` logs them and counts the batch as failed, dropping one batch rather
    than stopping its run loop, while the Pub/Sub worker nacks the message so it is
    redelivered.

    When ``sanitize.log_search_terms`` is enabled, every term the pass clears as
    ``PIIType.NON_PII`` is emitted to ``web.suggest.sanitized``. Terms of any other
    PII type are never logged, nor are terms without a query.
    """
    types: list[PIIType] = []
    # Queries still needing NER, and their positions in `types`.
    candidates: list[str] = []
    candidate_indices: list[int] = []

    for term in batch:
        query = term.query or ""

        # Exemption wins over detection by definition, and is the cheaper check.
        if query and exempts.is_exempt(query):
            types.append(PIIType.NON_PII)
            continue

        pii_type = basic_detect(query)
        if pii_type is PIIType.NON_PII and query:
            candidate_indices.append(len(types))
            candidates.append(query)
        types.append(pii_type)

    if candidates:
        detector = get_detector()
        executor = get_executor()
        chunk_size = settings.sanitize.ner_chunk_size
        for start in range(0, len(candidates), chunk_size):
            indices = candidate_indices[start : start + chunk_size]
            verdicts = await detect_person_batch(
                candidates[start : start + chunk_size], detector, executor
            )
            # `detect_person_batch` preserves input order, so verdicts align
            # positionally with `indices`. strict=True makes any future
            # violation of that contract fail loudly rather than mislabel terms.
            for index, is_person in zip(indices, verdicts, strict=True):
                if is_person:
                    types[index] = PIIType.PERSON

    # Aggregate before recording so a 512-term batch costs one counter add per
    # distinct PII type rather than one per term.
    for type_name, count in Counter(pii_type.name.lower() for pii_type in types).items():
        _sanitize_counter.add(count, {"type": type_name})

    # Log _only_ the sanitized search terms (i.e. those of PIIType.NON_PII)
    if LOG_SEARCH_TERMS:
        for term, pii_type in zip(batch, types, strict=True):
            if pii_type is PIIType.NON_PII and term.query:
                log_data = create_search_term_log(term)
                sanitized_term_logger.info("", extra=log_data.model_dump())
