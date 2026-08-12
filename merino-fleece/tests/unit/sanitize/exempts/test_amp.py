"""Unit tests for the AMP search term sanitization exempt."""

import asyncio
from typing import Any

import httpx
import pytest
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from pytest_mock import MockerFixture

from merino_common.testing.metrics import find_point
from merino_fleece.sanitize.exempts.amp import AmpExempt

AMP_LOGGER = "merino_fleece.sanitize.exempts.amp"
FETCH_METRIC = "sanitize.exempts.amp.fetch"
KEYWORDS_METRIC = "sanitize.exempts.amp.keywords"

# Stand-in for the request a real response would carry. `raise_for_status()` needs one.
REQUEST = httpx.Request("GET", "http://test-mars-api/data")


def suggestion(*keywords: Any) -> dict[str, Any]:
    """Build a minimal MARS suggestion record carrying `keywords`."""
    return {"advertiser": "Example.org", "keywords": list(keywords)}


def ok(*suggestions: dict[str, Any], etag: str | None = None) -> httpx.Response:
    """Build a 200 MARS response wrapping `suggestions`, optionally carrying an ETag."""
    return httpx.Response(
        200,
        json={"suggestions": list(suggestions)},
        headers={"ETag": etag} if etag else {},
        request=REQUEST,
    )


def not_modified() -> httpx.Response:
    """Build a 304 response, as MARS answers a matching `If-None-Match`."""
    return httpx.Response(304, request=REQUEST)


class MarsStub:
    """Stand-in for `httpx.AsyncClient.get` that answers per `country/form_factor`.

    Segments are fetched concurrently, so responses are keyed by segment rather than
    queued in call order. Each segment's list is consumed one response per fetch, and
    the final entry is repeated once exhausted, so a test only lists the responses whose
    ordering it actually cares about. An `Exception` entry is raised instead of returned.
    """

    def __init__(self, responses: dict[str, list[httpx.Response | Exception]]) -> None:
        self.responses = responses
        # (segment, request headers) for every call, in the order they were made.
        self.calls: list[tuple[str, dict[str, str]]] = []

    async def __call__(
        self, url: str, *, params: dict[str, str], headers: dict[str, str]
    ) -> httpx.Response:
        """Record the call and return (or raise) this segment's next response."""
        segment = f"{params['country']}/{params['form_factor']}"
        self.calls.append((segment, dict(headers)))
        queued = self.responses[segment]
        response = queued.pop(0) if len(queued) > 1 else queued[0]
        if isinstance(response, Exception):
            raise response
        return response

    @property
    def segments_called(self) -> list[str]:
        """Every segment fetched, in call order."""
        return [segment for segment, _ in self.calls]


def build_exempt(
    countries: list[str] | None = None, form_factors: list[str] | None = None
) -> AmpExempt:
    """Build an `AmpExempt` against the test MARS host."""
    return AmpExempt(
        base_url="http://test-mars-api/",
        suggestion_url_path="data",
        countries=countries or ["US"],
        form_factors=form_factors or ["desktop"],
        connect_timeout_sec=1.0,
        request_timeout_sec=2.0,
        resync_interval_sec=3600,
        cron_interval_sec=60,
    )


def install(mocker: MockerFixture, responses: dict[str, list[Any]]) -> MarsStub:
    """Patch `httpx.AsyncClient.get` with a `MarsStub` answering `responses`."""
    stub = MarsStub(responses)
    mocker.patch.object(httpx.AsyncClient, "get", stub)
    return stub


@pytest.fixture(name="exempt")
def fixture_exempt() -> AmpExempt:
    """Return a single-segment (`US/desktop`) exempt.

    The HTTP client is never closed because `get` is always mocked, so no connection is
    ever opened. `test_shutdown_cancels_cron_and_closes_client` covers the real teardown.
    """
    return build_exempt()


@pytest.mark.asyncio
async def test_fetch_populates_keywords(exempt: AmpExempt, mocker: MockerFixture) -> None:
    """Fetched keywords become exempt; everything else is left to be sanitized."""
    install(mocker, {"US/desktop": [ok(suggestion("firefox", "firefox account"))]})

    await exempt._fetch()

    assert exempt.is_exempt("firefox") is True
    assert exempt.is_exempt("firefox account") is True
    assert exempt.is_exempt("barack obama") is False


@pytest.mark.parametrize(
    "search_term",
    [
        pytest.param("Firefox Account", id="uppercase"),
        pytest.param("  firefox account", id="leading_whitespace"),
        pytest.param(" FIREFOX Account", id="both"),
    ],
)
@pytest.mark.asyncio
async def test_is_exempt_normalizes_the_search_term(
    exempt: AmpExempt, mocker: MockerFixture, search_term: str
) -> None:
    """Lookups are case- and leading-whitespace-insensitive.

    MARS keywords are lowercase, so a submitted term is normalized the same way merino's
    adm provider normalizes a query before looking it up. Trailing whitespace is left
    alone -- see `test_a_trailing_space_is_significant`.
    """
    install(mocker, {"US/desktop": [ok(suggestion("firefox account"))]})

    await exempt._fetch()

    assert exempt.is_exempt(search_term) is True


@pytest.mark.asyncio
async def test_a_trailing_space_is_significant(mocker: MockerFixture) -> None:
    """A term matches only the spacing MARS actually published.

    MARS serves AMP prefix states, so `'my '` (the user typed a space) and `'my'` are
    distinct keywords. Stripping the term would conflate them and exempt a term MARS never
    published a keyword for.
    """
    spaced, bare = build_exempt(), build_exempt()
    install(mocker, {"US/desktop": [ok(suggestion("my "))]})
    await spaced._fetch()
    install(mocker, {"US/desktop": [ok(suggestion("my"))]})
    await bare._fetch()

    assert spaced.is_exempt("my ") is True
    assert spaced.is_exempt("my") is False
    assert bare.is_exempt("my") is True
    assert bare.is_exempt("my ") is False


@pytest.mark.asyncio
async def test_keywords_are_unioned_across_segments(mocker: MockerFixture) -> None:
    """Every configured `country x form_factor` is fetched and unioned into one set.

    Duplicate config entries are collapsed first, so `dynaconf_merge` appending a country
    twice does not double the requests.
    """
    exempt = build_exempt(countries=["US", "DE", "US"], form_factors=["desktop", "phone"])
    stub = install(
        mocker,
        {
            "US/desktop": [ok(suggestion("firefox"))],
            "US/phone": [ok(suggestion("firefox mobile"))],
            "DE/desktop": [ok(suggestion("feuerfuchs"))],
            "DE/phone": [ok(suggestion("feuerfuchs mobil"))],
        },
    )

    await exempt._fetch()

    assert sorted(stub.segments_called) == ["DE/desktop", "DE/phone", "US/desktop", "US/phone"]
    assert exempt.keywords == frozenset(
        {"firefox", "firefox mobile", "feuerfuchs", "feuerfuchs mobil"}
    )


@pytest.mark.asyncio
async def test_not_modified_segment_keeps_its_keywords(mocker: MockerFixture) -> None:
    """A 304 on one segment does not drop its keywords when another returns fresh data.

    This is why keywords are stored per segment. Rebuilding the flat set from only the
    segments that answered 200 would silently discard every 304'd segment.
    """
    exempt = build_exempt(countries=["US", "DE"])
    install(
        mocker,
        {
            "US/desktop": [ok(suggestion("firefox"), etag="us-v1"), not_modified()],
            "DE/desktop": [ok(suggestion("feuerfuchs")), ok(suggestion("feuerfuchs neu"))],
        },
    )

    await exempt._fetch()
    await exempt._fetch()

    assert exempt.is_exempt("firefox") is True, "the 304'd segment must keep its keywords"
    assert exempt.is_exempt("feuerfuchs neu") is True
    assert exempt.is_exempt("feuerfuchs") is False, "the refreshed segment must be replaced"


@pytest.mark.asyncio
async def test_etag_is_sent_on_the_next_fetch(exempt: AmpExempt, mocker: MockerFixture) -> None:
    """An ETag from a 200 is echoed back as `If-None-Match`, and a 304 does not clear it."""
    stub = install(
        mocker,
        {"US/desktop": [ok(suggestion("firefox"), etag="v1"), not_modified(), not_modified()]},
    )

    await exempt._fetch()
    await exempt._fetch()
    await exempt._fetch()

    assert [headers.get("If-None-Match") for _, headers in stub.calls] == [None, "v1", "v1"]


@pytest.mark.asyncio
async def test_etag_is_not_stored_for_an_unusable_response(
    exempt: AmpExempt, mocker: MockerFixture
) -> None:
    """A payload that could not be parsed leaves the ETag unset.

    Storing it would pin the segment to data that was never used: the next fetch would
    answer 304 and the keywords would stay empty forever.
    """
    stub = install(
        mocker,
        {
            "US/desktop": [
                httpx.Response(200, content=b"not json", headers={"ETag": "v1"}, request=REQUEST),
                ok(suggestion("firefox"), etag="v2"),
            ]
        },
    )

    await exempt._fetch()
    await exempt._fetch()

    assert [headers.get("If-None-Match") for _, headers in stub.calls] == [None, None]
    assert exempt.is_exempt("firefox") is True


@pytest.mark.asyncio
async def test_fetch_failure_keeps_previous_keywords(
    exempt: AmpExempt, mocker: MockerFixture
) -> None:
    """A failed refresh serves the last known keywords and retries on the next tick.

    `last_fetch_at` is deliberately not advanced by a failure, so the refresh stays due
    and the cron job retries at its own (much shorter) interval rather than waiting out
    another full resync interval.
    """
    install(
        mocker,
        {"US/desktop": [ok(suggestion("firefox")), httpx.ConnectError("MARS is down")]},
    )

    await exempt._fetch()
    # Age the successful fetch so the failing one below is a refresh that was due.
    exempt.last_fetch_at -= exempt.resync_interval_sec
    fetched_at = exempt.last_fetch_at

    await exempt._fetch()

    assert exempt.is_exempt("firefox") is True
    assert exempt.last_fetch_at == fetched_at
    assert exempt._should_fetch() is True


@pytest.mark.asyncio
async def test_healthy_segments_survive_an_unhealthy_one(mocker: MockerFixture) -> None:
    """One failing segment does not discard the results of the others."""
    exempt = build_exempt(countries=["US", "DE"])
    install(
        mocker,
        {
            "US/desktop": [ok(suggestion("firefox"))],
            "DE/desktop": [httpx.ConnectError("MARS is down")],
        },
    )

    await exempt._fetch()

    assert exempt.is_exempt("firefox") is True
    assert exempt.last_fetch_at == 0.0, "a partial failure must leave the retry pending"


@pytest.mark.asyncio
async def test_no_data_means_nothing_is_exempt(exempt: AmpExempt, mocker: MockerFixture) -> None:
    """With no keywords ever fetched, every search term is sanitized as non-exempt."""
    install(mocker, {"US/desktop": [httpx.ConnectError("MARS is down")]})

    await exempt._fetch()

    assert exempt.keywords == frozenset()
    assert exempt.is_exempt("firefox") is False


@pytest.mark.parametrize(
    "response",
    [
        pytest.param(
            httpx.Response(200, content=b"not json", request=REQUEST),
            id="invalid_json",
        ),
        pytest.param(
            httpx.Response(200, json={"data": []}, request=REQUEST),
            id="missing_suggestions_key",
        ),
        pytest.param(
            httpx.Response(200, json={"suggestions": ["firefox"]}, request=REQUEST),
            id="suggestions_not_records",
        ),
        pytest.param(
            httpx.Response(200, json={"suggestions": [{"keywords": [42]}]}, request=REQUEST),
            id="keyword_not_a_string",
        ),
        pytest.param(
            # The reason this exempt validates at all: iterated as a sequence, a scalar
            # string would seed the keyword set with its own single characters, exempting
            # real search terms from sanitization.
            httpx.Response(200, json={"suggestions": [{"keywords": "firefox"}]}, request=REQUEST),
            id="keywords_scalar_string",
        ),
        pytest.param(
            httpx.Response(200, json={"suggestions": [{"keywords": None}]}, request=REQUEST),
            id="keywords_null",
        ),
        pytest.param(httpx.Response(500, request=REQUEST), id="server_error"),
        pytest.param(httpx.Response(404, request=REQUEST), id="not_found"),
    ],
)
@pytest.mark.asyncio
async def test_unusable_responses_keep_the_previous_keywords(
    exempt: AmpExempt,
    mocker: MockerFixture,
    caplog: pytest.LogCaptureFixture,
    response: httpx.Response,
) -> None:
    """A malformed or failing response is logged and leaves the served keywords intact."""
    install(mocker, {"US/desktop": [ok(suggestion("firefox")), response]})

    await exempt._fetch()
    # Age the successful fetch so the unusable response below is a refresh that was due.
    exempt.last_fetch_at -= exempt.resync_interval_sec

    await exempt._fetch()

    assert exempt.is_exempt("firefox") is True
    assert exempt._should_fetch() is True, "an unusable response must be retried"
    assert [record.message for record in caplog.records if record.name == AMP_LOGGER]


@pytest.mark.asyncio
async def test_empty_suggestions_keep_the_previous_keywords(
    exempt: AmpExempt, mocker: MockerFixture
) -> None:
    """An empty payload is treated as "no new data" rather than a failure.

    MARS answering with zero suggestions is not an error, so the refresh is considered
    complete and the next one waits out the full resync interval.
    """
    install(mocker, {"US/desktop": [ok(suggestion("firefox")), ok()]})

    await exempt._fetch()
    await exempt._fetch()

    assert exempt.is_exempt("firefox") is True
    assert exempt._should_fetch() is False


@pytest.mark.asyncio
async def test_records_without_keywords_are_skipped(
    exempt: AmpExempt, mocker: MockerFixture
) -> None:
    """A record omitting `keywords` contributes nothing and breaks nothing.

    Omission is tolerated because it costs nothing to tolerate. A `keywords` present but of
    the wrong type is not -- that is a contract violation, covered by
    `test_unusable_responses_keep_the_previous_keywords`.
    """
    install(mocker, {"US/desktop": [ok({"advertiser": "Example.org"}, suggestion("firefox"))]})

    await exempt._fetch()

    assert exempt.keywords == frozenset({"firefox"})


@pytest.mark.asyncio
async def test_should_fetch_respects_the_resync_interval(
    exempt: AmpExempt, mocker: MockerFixture
) -> None:
    """A refresh is due once `resync_interval_sec` has elapsed since the last one."""
    install(mocker, {"US/desktop": [ok(suggestion("firefox"))]})

    assert exempt._should_fetch() is True, "a never-fetched exempt is always due"

    await exempt._fetch()
    assert exempt._should_fetch() is False

    exempt.last_fetch_at -= exempt.resync_interval_sec
    assert exempt._should_fetch() is True


@pytest.mark.asyncio
async def test_initialize_fetches_before_starting_the_cron(
    exempt: AmpExempt, mocker: MockerFixture
) -> None:
    """Keywords are available as soon as `initialize` returns, not on the first tick."""
    install(mocker, {"US/desktop": [ok(suggestion("firefox"))]})

    await exempt.initialize()
    try:
        assert exempt.is_exempt("firefox") is True
        assert exempt.cron_task is not None
    finally:
        await exempt.shutdown()


@pytest.mark.asyncio
async def test_initialize_survives_a_failed_first_fetch(
    exempt: AmpExempt, mocker: MockerFixture
) -> None:
    """A MARS outage at startup is not fatal; the cron job still runs to retry."""
    install(mocker, {"US/desktop": [httpx.ConnectError("MARS is down")]})

    await exempt.initialize()
    try:
        assert exempt.is_exempt("firefox") is False
        assert exempt.cron_task is not None
        assert exempt._should_fetch() is True
    finally:
        await exempt.shutdown()


@pytest.mark.asyncio
async def test_initialize_survives_an_unexpected_fetch_error(
    exempt: AmpExempt, mocker: MockerFixture, caplog: pytest.LogCaptureFixture
) -> None:
    """An error the per-segment handling does not cover still leaves the exempt usable."""
    mocker.patch.object(exempt, "_fetch", side_effect=RuntimeError("boom"))

    await exempt.initialize()
    try:
        assert exempt.last_fetch_at == 0
        assert exempt.cron_task is not None
        assert "Failed to fetch AMP keywords from MARS" in caplog.text
    finally:
        await exempt.shutdown()


@pytest.mark.asyncio
async def test_the_cron_job_refreshes_keywords(exempt: AmpExempt, mocker: MockerFixture) -> None:
    """The cron job picks up a new dataset once a refresh is due.

    The intervals are collapsed so the job ticks immediately: the first fetch happens in
    `initialize`, and the tick that follows finds the resync already due.
    """
    exempt.resync_interval_sec = 0
    exempt.cron_interval_sec = 0
    install(mocker, {"US/desktop": [ok(suggestion("firefox")), ok(suggestion("thunderbird"))]})

    await exempt.initialize()
    try:
        # Yield to the loop until the cron task has worked through a tick. Bounded so a
        # broken wiring fails the assertion below instead of hanging.
        for _ in range(50):
            await asyncio.sleep(0)
            if exempt.is_exempt("thunderbird"):
                break
        assert exempt.is_exempt("thunderbird") is True
    finally:
        await exempt.shutdown()


@pytest.mark.asyncio
async def test_shutdown_cancels_the_cron_and_closes_the_client(
    exempt: AmpExempt, mocker: MockerFixture
) -> None:
    """Teardown leaves neither a running task nor an open connection pool behind."""
    install(mocker, {"US/desktop": [ok(suggestion("firefox"))]})
    await exempt.initialize()
    cron_task = exempt.cron_task

    await exempt.shutdown()

    assert cron_task is not None and cron_task.cancelled()
    assert exempt.cron_task is None
    assert exempt.http_client.is_closed is True


@pytest.mark.asyncio
async def test_shutdown_without_initialize_closes_the_client(exempt: AmpExempt) -> None:
    """Shutting down an exempt that never started is a no-op beyond closing the client."""
    await exempt.shutdown()

    assert exempt.http_client.is_closed is True


@pytest.mark.asyncio
async def test_fetch_records_metrics(
    exempt: AmpExempt, mocker: MockerFixture, metric_reader: InMemoryMetricReader
) -> None:
    """Each segment fetch is counted by outcome, and the keyword count is gauged."""
    install(
        mocker,
        {
            "US/desktop": [
                ok(suggestion("firefox", "thunderbird"), etag="v1"),
                not_modified(),
                httpx.ConnectError("MARS is down"),
            ]
        },
    )
    tags = {"country": "US", "form_factor": "desktop"}

    await exempt._fetch()
    gauge = find_point(metric_reader, KEYWORDS_METRIC)
    assert gauge is not None and gauge.value == 2

    before = find_point(metric_reader, FETCH_METRIC, **tags, status="success")
    assert before is not None and before.value >= 1

    await exempt._fetch()
    await exempt._fetch()

    for status in ("not_modified", "error"):
        point = find_point(metric_reader, FETCH_METRIC, **tags, status=status)
        assert point is not None and point.value >= 1, f"missing a {status} data point"
