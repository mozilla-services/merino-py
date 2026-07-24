"""Helpers for asserting on OpenTelemetry metrics via an ``InMemoryMetricReader``.

These utilities read back the metrics collected by an
``opentelemetry.sdk.metrics.export.InMemoryMetricReader`` so tests can assert on
counter/gauge values and data-point attributes without mocking the instruments.
"""

from collections.abc import Iterator

from opentelemetry.sdk.metrics.export import (
    Gauge,
    InMemoryMetricReader,
    Metric,
    NumberDataPoint,
    Sum,
)


def _iter_metrics(reader: InMemoryMetricReader) -> Iterator[Metric]:
    """Yield every collected ``Metric`` across all resources and scopes."""
    data = reader.get_metrics_data()
    if data is None:
        return
    for resource_metric in data.resource_metrics:
        for scope_metric in resource_metric.scope_metrics:
            yield from scope_metric.metrics


def collect_metrics(reader: InMemoryMetricReader) -> dict[str, float]:
    """Collect Sum/Gauge metrics into a ``{name: summed-value}`` dict."""
    values: dict[str, float] = {}
    for metric in _iter_metrics(reader):
        if isinstance(metric.data, (Sum, Gauge)):
            values[metric.name] = sum((p.value for p in metric.data.data_points), 0.0)
    return values


def number_points(reader: InMemoryMetricReader, name: str) -> list[NumberDataPoint]:
    """Return the ``NumberDataPoint``s for the named Sum/Gauge metric."""
    points: list[NumberDataPoint] = []
    for metric in _iter_metrics(reader):
        if metric.name == name and isinstance(metric.data, (Sum, Gauge)):
            points.extend(metric.data.data_points)
    return points


def find_point(reader: InMemoryMetricReader, name: str, **match: object) -> NumberDataPoint | None:
    """Return the single data point for ``name`` whose attributes match all of ``match``.

    Data point order is not guaranteed, so tests select by attributes rather than
    index.
    """
    for point in number_points(reader, name):
        attributes = point.attributes or {}
        if all(attributes.get(key) == value for key, value in match.items()):
            return point
    return None


def counter_value(reader: InMemoryMetricReader, name: str) -> float:
    """Sum the data points of the named counter metric collected by the reader."""
    return sum((point.value for point in number_points(reader, name)), 0.0)
