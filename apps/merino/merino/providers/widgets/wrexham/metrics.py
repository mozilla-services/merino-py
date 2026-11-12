"""OpenTelemetry instruments for the Wrexham ingestion job and widget API.

These are no-ops unless an OpenTelemetry `MeterProvider` is configured, e.g. by the
OpenTelemetry operator's auto-instrumentation in Kubernetes.
"""

from collections.abc import Iterable

from circuitbreaker import CircuitBreaker
from opentelemetry import metrics
from opentelemetry.metrics import CallbackOptions, Observation

_meter = metrics.get_meter("merino.widgets.wrexham")

# Histogram bucket boundaries in seconds, shared by the refresh duration and the data age. They
# grow roughly logarithmically (about 2-2.5x per step), rounded to readable values: fine-grained
# for sub-second refreshes and fresh live data, then whole minutes and hours up to 24 hours for
# stale data.
DURATION_BUCKETS_SEC: tuple[float, ...] = (
    0.01, 0.025, 0.05, 0.1, 0.25, 0.5,  # Sub-second
    1, 2.5, 5, 10, 30,  # Seconds
    60, 120, 300, 600, 1200, 1800,  # Minutes
    3600, 7200, 14400, 28800, 43200, 86400,  # Hours, up to 24
)  # fmt: skip

# Job metrics. Tagged by `data_type`: "fixtures", "live_matches" or "standings".

job_refresh_count = _meter.create_counter(
    name="merino.wrexham.job.refresh.count",
    unit="{refresh}",
    description="Wrexham data refreshes, by data type and result (success, failure, or canceled).",
)

job_refresh_duration = _meter.create_histogram(
    name="merino.wrexham.job.refresh.duration",
    unit="s",
    description="Time taken to refresh Wrexham data, by data type.",
    explicit_bucket_boundaries_advisory=DURATION_BUCKETS_SEC,
)

job_last_synced_at = _meter.create_gauge(
    name="merino.wrexham.job.last_synced_at",
    unit="s",
    description="Unix timestamp when Wrexham data was last refreshed successfully, by data type.",
)

# API metrics. Tagged by `endpoint`: "matches" or "standings".

api_redis_error_count = _meter.create_counter(
    name="merino.wrexham.api.redis_errors.count",
    unit="{error}",
    description="Failed reads of Wrexham data from Redis, by endpoint.",
)

api_data_age = _meter.create_histogram(
    name="merino.wrexham.api.data_age",
    unit="s",
    description=(
        "Age of the Wrexham data served (now - fetched_at), by endpoint and data type, and by "
        "competition for fixtures."
    ),
    explicit_bucket_boundaries_advisory=DURATION_BUCKETS_SEC,
)


def observe_circuit_breaker(breaker: CircuitBreaker) -> None:
    """Report whether `breaker` is open as a gauge, read each time metrics are exported.

    The gauge is 1 while the breaker is open and rejecting reads, and 0 while it's closed or
    half-open. It isn't tagged by endpoint, because both endpoints share the breaker.
    """

    def observe(_options: CallbackOptions) -> Iterable[Observation]:
        return [Observation(circuit_breaker_open_value(breaker))]

    _meter.create_observable_gauge(
        name="merino.wrexham.api.circuit_breaker.open",
        callbacks=[observe],
        unit="1",
        description="Whether the Wrexham circuit breaker is open (1) or not (0).",
    )


def circuit_breaker_open_value(breaker: CircuitBreaker) -> int:
    """Return the circuit breaker gauge's value: 1 if `breaker` is open, otherwise 0."""
    return 1 if breaker.opened else 0
