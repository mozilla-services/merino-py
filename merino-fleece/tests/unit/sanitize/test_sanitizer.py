"""Unit tests for the shared search term sanitization pass."""

import logging
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pytest
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from pytest_mock import MockerFixture

from merino_common.models.suggest_logging import SuggestRequestParams
from merino_common.testing.metrics import number_points
from merino_fleece.sanitize import exempts, sanitizer
from merino_fleece.sanitize.sanitizer import sanitize_batch

ParamsFactory = Callable[[str | None], SuggestRequestParams]

SANITIZE_METRIC = "search_terms.sanitize"

SANITIZED_LOGGER = "web.suggest.sanitized"


@pytest.fixture(name="params")
def fixture_params() -> ParamsFactory:
    """Return a factory that builds a minimal SuggestRequestParams for a given query."""

    def _build(query: str | None) -> SuggestRequestParams:
        return SuggestRequestParams(
            query=query,
            code=200,
            rid="rid",
            client_variants="",
            requested_providers="",
            browser="Firefox",
            os_family="macos",
            form_factor="desktop",
        )

    return _build


@pytest.fixture
def executor() -> Iterator[ThreadPoolExecutor]:
    """Yield a single-worker pool mirroring the app's default NER pool size."""
    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="test-pii-detect")
    yield pool
    pool.shutdown(wait=True)


class RecordingDetector:
    """Detector stub returning preset verdicts and recording every batch it receives."""

    def __init__(self, verdicts: dict[str, bool] | None = None) -> None:
        """Store per-query verdicts (defaulting to False) and init the call log."""
        self.verdicts = verdicts or {}
        self.batch_calls: list[list[str]] = []

    def is_person_batch(self, texts: list[str]) -> list[bool]:
        """Record the batch and return each text's configured verdict."""
        self.batch_calls.append(list(texts))
        return [self.verdicts.get(text, False) for text in texts]

    @property
    def seen_queries(self) -> list[str]:
        """Every query handed to the detector, flattened across chunks."""
        return [query for call in self.batch_calls for query in call]


class StubExempt:
    """Exempt stub covering a fixed set of search terms."""

    def __init__(self, *terms: str) -> None:
        """Store the terms this exempt covers."""
        self.terms = set(terms)

    async def initialize(self) -> None:
        """Nothing to bootstrap; the terms are fixed at construction."""

    async def shutdown(self) -> None:
        """Nothing to tear down."""

    def is_exempt(self, search_term: str) -> bool:
        """Return whether the term is one of this stub's."""
        return search_term in self.terms


@pytest.fixture(name="register_exempt")
def fixture_register_exempt() -> Iterator[Callable[..., None]]:
    """Return a helper that registers an exempt for the duration of a test.

    The registry is process-wide, so it is cleared afterwards to keep exemptions from
    leaking into the tests that follow.
    """

    def _register(*terms: str) -> None:
        exempts.register(StubExempt(*terms))

    yield _register
    exempts._exempts.clear()


@pytest.fixture
def detector(monkeypatch: pytest.MonkeyPatch, executor: ThreadPoolExecutor) -> RecordingDetector:
    """Install a recording detector and the test pool as the pass's NER singletons.

    The pass looks these up per batch rather than capturing them up front, so patching
    the module's accessors is enough -- no app lifespan required.
    """
    stub = RecordingDetector()
    monkeypatch.setattr(sanitizer, "get_detector", lambda: stub)
    monkeypatch.setattr(sanitizer, "get_executor", lambda: executor)
    return stub


def counter_by_type(reader: InMemoryMetricReader) -> dict[str, float]:
    """Return the sanitize counter's current value per `type` attribute."""
    totals: dict[str, float] = {}
    for point in number_points(reader, SANITIZE_METRIC):
        attributes = point.attributes or {}
        pii_type = str(attributes.get("type"))
        totals[pii_type] = totals.get(pii_type, 0.0) + point.value
    return totals


def delta(before: dict[str, float], after: dict[str, float], pii_type: str) -> float:
    """Return how much the counter for `pii_type` grew between two snapshots."""
    return after.get(pii_type, 0.0) - before.get(pii_type, 0.0)


@pytest.fixture
def log_search_terms(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    """Turn the sanitized search term data log on and capture it at INFO.

    The pass reads the toggle once at import, mirroring merino's logging
    middleware, so tests flip the module attribute rather than the setting.
    """
    monkeypatch.setattr(sanitizer, "LOG_SEARCH_TERMS", True)
    caplog.set_level(logging.INFO, logger=SANITIZED_LOGGER)


def sanitized_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    """Return the records emitted to the sanitized search term data log."""
    return [record for record in caplog.records if record.name == SANITIZED_LOGGER]


def logged_queries(caplog: pytest.LogCaptureFixture) -> list[str]:
    """Return the query of every sanitized search term logged, in emission order."""
    return [str(record.query) for record in sanitized_records(caplog)]  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("query", "is_person", "expected_type", "expects_ner"),
    [
        pytest.param("alice@example.com", False, "email", False, id="email"),
        pytest.param("iphone 15 review", False, "numeric", False, id="numeric"),
        pytest.param("barack obama", True, "person", True, id="person"),
        pytest.param("the weather today", False, "non_pii", True, id="non_pii"),
        pytest.param("", False, "non_pii", False, id="empty"),
        pytest.param(None, False, "non_pii", False, id="none"),
    ],
)
@pytest.mark.asyncio
async def test_classification(
    detector: RecordingDetector,
    params: ParamsFactory,
    metric_reader: InMemoryMetricReader,
    query: str | None,
    is_person: bool,
    expected_type: str,
    expects_ner: bool,
) -> None:
    """Each search term is counted under its detected PII type.

    `expects_ner` pins the short-circuit: only queries the cheap pattern pass clears
    should reach SpaCy, since NER is by far the expensive step.
    """
    if is_person:
        detector.verdicts[str(query)] = True
    before = counter_by_type(metric_reader)

    await sanitize_batch([params(query)])

    after = counter_by_type(metric_reader)
    assert delta(before, after, expected_type) == 1
    assert detector.seen_queries == ([query] if expects_ner else [])


@pytest.mark.asyncio
async def test_mixed_batch_maps_verdicts_to_the_right_terms(
    detector: RecordingDetector,
    params: ParamsFactory,
    metric_reader: InMemoryMetricReader,
) -> None:
    """Every term in a mixed batch is counted under its own type.

    Only a subset of the batch reaches NER, so verdicts are indexed against the
    filtered candidate list rather than the batch itself. This is the case that
    catches an off-by-one in that mapping: `charlie chaplin` is the only PERSON, and
    it sits after two terms that skipped NER entirely.
    """
    detector.verdicts["charlie chaplin"] = True
    batch = [
        params("the weather today"),  # non_pii, goes to NER
        params("alice@example.com"),  # email, skips NER
        params("iphone 15"),  # numeric, skips NER
        params("charlie chaplin"),  # person, goes to NER
        params(None),  # non_pii, skips NER
        params("best pizza"),  # non_pii, goes to NER
    ]
    before = counter_by_type(metric_reader)

    await sanitize_batch(batch)

    after = counter_by_type(metric_reader)
    assert delta(before, after, "email") == 1
    assert delta(before, after, "numeric") == 1
    assert delta(before, after, "person") == 1
    assert delta(before, after, "non_pii") == 3
    assert detector.seen_queries == ["the weather today", "charlie chaplin", "best pizza"]


@pytest.mark.asyncio
async def test_exempt_terms_skip_detection(
    detector: RecordingDetector,
    params: ParamsFactory,
    metric_reader: InMemoryMetricReader,
    register_exempt: Callable[..., None],
    mocker: MockerFixture,
) -> None:
    """An exempt term is counted `non_pii` without any detection running.

    Skipping the work is the whole point of an exemption, so both the cheap pattern pass
    and NER are asserted to be bypassed -- a term that merely happens to be classified
    `non_pii` would not prove anything.
    """
    register_exempt("firefox accounts")
    basic_detect = mocker.spy(sanitizer, "basic_detect")
    before = counter_by_type(metric_reader)

    await sanitize_batch([params("firefox accounts")])

    after = counter_by_type(metric_reader)
    assert delta(before, after, "non_pii") == 1
    assert basic_detect.call_count == 0
    assert detector.seen_queries == []


@pytest.mark.asyncio
async def test_exemption_wins_over_detection(
    detector: RecordingDetector,
    params: ParamsFactory,
    metric_reader: InMemoryMetricReader,
    register_exempt: Callable[..., None],
) -> None:
    """An exempt term that looks like PII is still exempt.

    Exemption is an assertion that the term is safe by provenance, so it takes precedence
    over what the detectors would have made of it.
    """
    register_exempt("iphone 15")
    before = counter_by_type(metric_reader)

    await sanitize_batch([params("iphone 15")])

    after = counter_by_type(metric_reader)
    assert delta(before, after, "numeric") == 0
    assert delta(before, after, "non_pii") == 1


@pytest.mark.asyncio
async def test_non_exempt_terms_in_a_mixed_batch_are_still_sanitized(
    detector: RecordingDetector,
    params: ParamsFactory,
    metric_reader: InMemoryMetricReader,
    register_exempt: Callable[..., None],
) -> None:
    """Exempting some terms does not disturb the classification of the rest.

    Exempt terms are dropped from the NER candidate list, so this also guards the index
    mapping between candidates and their positions in the batch.
    """
    register_exempt("firefox accounts", "thunderbird")
    detector.verdicts["charlie chaplin"] = True
    batch = [
        params("firefox accounts"),  # exempt
        params("alice@example.com"),  # email, skips NER
        params("thunderbird"),  # exempt
        params("charlie chaplin"),  # person, goes to NER
        params("best pizza"),  # non_pii, goes to NER
    ]
    before = counter_by_type(metric_reader)

    await sanitize_batch(batch)

    after = counter_by_type(metric_reader)
    assert delta(before, after, "email") == 1
    assert delta(before, after, "person") == 1
    assert delta(before, after, "non_pii") == 3  # two exempt plus `best pizza`
    assert detector.seen_queries == ["charlie chaplin", "best pizza"]


@pytest.mark.asyncio
async def test_ner_is_chunked(
    monkeypatch: pytest.MonkeyPatch,
    detector: RecordingDetector,
    params: ParamsFactory,
    metric_reader: InMemoryMetricReader,
) -> None:
    """Candidates are split into `ner_chunk_size` calls, and verdicts still land right.

    Chunking releases the shared NER thread between calls so concurrent /pii requests
    are not stuck behind one long batch. The PERSON hit is in the final, partial chunk
    to prove the index mapping survives chunk boundaries.
    """
    monkeypatch.setitem(sanitizer.settings.sanitize, "ner_chunk_size", 2)
    detector.verdicts["ada lovelace"] = True
    queries = ["one", "two", "three", "four", "ada lovelace"]
    before = counter_by_type(metric_reader)

    await sanitize_batch([params(query) for query in queries])

    assert [len(call) for call in detector.batch_calls] == [2, 2, 1]
    assert detector.seen_queries == queries
    after = counter_by_type(metric_reader)
    assert delta(before, after, "person") == 1
    assert delta(before, after, "non_pii") == 4


@pytest.mark.asyncio
async def test_empty_batch_skips_detection(detector: RecordingDetector) -> None:
    """An empty batch does no work and records nothing."""
    await sanitize_batch([])
    assert detector.batch_calls == []


@pytest.mark.usefixtures("log_search_terms")
@pytest.mark.asyncio
async def test_only_non_pii_terms_are_logged(
    detector: RecordingDetector,
    params: ParamsFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Only the terms sanitization clears reach the data log.

    This is the privacy-critical assertion: anything the pass flags as PII of any
    kind must never be written out, so the mixed batch covers every detected type.
    """
    detector.verdicts["charlie chaplin"] = True
    batch = [
        params("the weather today"),  # non_pii
        params("alice@example.com"),  # email
        params("iphone 15"),  # numeric
        params("charlie chaplin"),  # person
        params(None),  # non_pii, but no query
        params("best pizza"),  # non_pii
    ]

    await sanitize_batch(batch)

    assert logged_queries(caplog) == ["the weather today", "best pizza"]


@pytest.mark.usefixtures("log_search_terms")
@pytest.mark.asyncio
async def test_ner_flagged_person_is_not_logged(
    detector: RecordingDetector,
    params: ParamsFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A term only NER catches stays out of the log.

    `basic_detect` clears a plain name, so this term is a NON_PII candidate right up
    until the NER pass upgrades it. Logging any earlier than that would leak it.
    """
    detector.verdicts["barack obama"] = True

    await sanitize_batch([params("barack obama")])

    assert sanitized_records(caplog) == []


@pytest.mark.asyncio
async def test_logging_is_off_by_default(
    detector: RecordingDetector,
    params: ParamsFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """With the toggle off, even a cleared term is not logged."""
    caplog.set_level(logging.INFO, logger=SANITIZED_LOGGER)

    await sanitize_batch([params("the weather today")])

    assert sanitized_records(caplog) == []


@pytest.mark.usefixtures("log_search_terms")
@pytest.mark.parametrize("query", [None, ""], ids=["none", "empty"])
@pytest.mark.asyncio
async def test_queryless_terms_are_skipped_but_still_counted(
    detector: RecordingDetector,
    params: ParamsFactory,
    metric_reader: InMemoryMetricReader,
    caplog: pytest.LogCaptureFixture,
    query: str | None,
) -> None:
    """A term without a query is counted as non_pii but has nothing to log."""
    before = counter_by_type(metric_reader)

    await sanitize_batch([params(query)])

    after = counter_by_type(metric_reader)
    assert delta(before, after, "non_pii") == 1
    assert sanitized_records(caplog) == []


@pytest.mark.usefixtures("log_search_terms")
@pytest.mark.asyncio
async def test_log_record_shape(
    detector: RecordingDetector, caplog: pytest.LogCaptureFixture
) -> None:
    """The emitted record carries the expected name, level, and request fields.

    `sensitive` is asserted on the record rather than on the model, so the flag is
    proven to survive the `model_dump()` hop into `extra=`. Without it the record
    would flow to the generally accessible log inspection interfaces.

    `timestamp` is asserted here for the same reason: it is the name the BigQuery
    dataset reads, it must arrive as a str rather than a datetime, and `extra=` rejects
    keys that collide with reserved `LogRecord` attributes.
    """
    term = SuggestRequestParams(
        query="the weather today",
        code=200,
        rid="request-id",
        session_id="session-id",
        sequence_no=3,
        client_variants="variant",
        requested_providers="adm",
        country="US",
        region="CA",
        city="San Francisco",
        dma=807,
        browser="Firefox(120)",
        os_family="macos",
        form_factor="desktop",
        submitted_at=datetime(2022, 12, 18, hour=15, minute=58, second=41, tzinfo=UTC),
    )

    await sanitize_batch([term])

    [record] = sanitized_records(caplog)
    assert record.levelno == logging.INFO
    assert record.message == ""
    assert record.sensitive is True  # type: ignore[attr-defined]
    assert record.query == "the weather today"  # type: ignore[attr-defined]
    assert record.request_id == "request-id"  # type: ignore[attr-defined]
    assert record.timestamp == "2022-12-18T15:58:41+00:00"  # type: ignore[attr-defined]
    assert not hasattr(record, "submitted_at")  # renamed at the log boundary
    assert record.session_id == "session-id"  # type: ignore[attr-defined]
    assert record.sequence_no == 3  # type: ignore[attr-defined]
    assert record.country == "US"  # type: ignore[attr-defined]
    assert record.region == "CA"  # type: ignore[attr-defined]
    assert record.city == "San Francisco"  # type: ignore[attr-defined]
    assert record.dma == 807  # type: ignore[attr-defined]
    assert record.browser == "Firefox(120)"  # type: ignore[attr-defined]
    assert record.os_family == "macos"  # type: ignore[attr-defined]
    assert record.form_factor == "desktop"  # type: ignore[attr-defined]
