# This is a config
# pragma: no cover

from opentelemetry import metrics

_meter = metrics.get_meter("merino.sports.sportsdata")

# Gauge for when data was last synced from remote endpoint
last_synced_at = _meter.create_gauge(
    "merino.sports.sportsdata.endpoint.last_synced_at",
    unit="s",
    description="Unix timestamp when sportsdata endpoint was last synced successfully",
)
# Job state tracking for world cup etl
wcs_job_state_counter = _meter.create_counter(
    "merino.sports.sportsdata.endpoint.wcs_job_state",
    description="Job history (failed/succeeded) for WCS polls",
)
