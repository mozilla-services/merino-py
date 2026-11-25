"""OpenTelemetry instruments for hook-eye's checks.

Values read from a monitored system use observable instruments that report the check's
latest snapshot, because:

* A synchronous instrument keeps exporting every series it has recorded (cumulative
  temporality, per the OpenTelemetry spec), so deleted resources and failed runs would
  report stale values. Observable series disappear instead; treat a missing series as
  unhealthy.
* Only an observable counter can export a running total as-is.

Events in hook-eye itself, like each check's run counter, use synchronous instruments.

The OpenTelemetry operator (or `opentelemetry-instrument` locally) configures the SDK;
without it, every instrument is a no-op.
"""

from opentelemetry import metrics

meter = metrics.get_meter("merino-hook-eye")
