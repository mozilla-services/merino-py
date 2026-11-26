# Merino-hook-eye

A small, single-replica service for monitoring that Merino's own metrics and the OpenTelemetry
Collector receivers can't cover (see @apps/hook-eye/README.md for the criteria). Its only check
today scrapes `GET _ccr/stats` on a follower Elasticsearch cluster and emits cross-cluster
replication health metrics. It's one of the member packages of the **merino-py** monorepo.

Each check lives in its own subpackage with its own cron job; the CCR check is in
@apps/hook-eye/merino_hook_eye/ccr/. See "Adding a check" in @docs/dev/hook-eye.md.

## Code Structure

- **App**, @apps/hook-eye/merino_hook_eye/app.py. No API of its own; the FastAPI app only
  serves the Dockerflow endpoints for Kubernetes probes. `CHECKS` registers every check by the
  name of its settings section; the lifespan starts those whose section sets `enabled`. It replaces the shared
  `/__heartbeat__` with one that fails when an enabled check's loop dies or stalls.
- **Checks**, @apps/hook-eye/merino_hook_eye/checks.py. `run_check` runs one check on a
  `merino_common.utils.cron.Job` and returns a `RunningCheck` the heartbeat inspects.
- **Metrics**, @apps/hook-eye/merino_hook_eye/metrics.py. The shared meter, and why values
  read from a monitored system use observable instruments. Don't switch those to synchronous
  instruments. Document every metric in @apps/hook-eye/metrics.yaml.
- **CCR check**, @apps/hook-eye/merino_hook_eye/ccr/:
  - `follower.py`: the `ccr_follower` check. Builds the follower client and runs the scraper
    every `[default.ccr_follower] interval_sec`.
  - `stats.py`: frozen Pydantic models for the reported parts of the `_ccr/stats` response,
    and the parser that filters follower indices by `[default.ccr_follower] index_patterns`.
  - `scraper.py`: fetches and parses one response, then publishes it as the metrics
    snapshot. A failure clears the snapshot and re-raises.
  - `metrics.py`: the CCR instruments, whose callbacks read the latest snapshot.

OpenTelemetry is configured by the Kubernetes operator in deployed environments and by
`make dev-hook-eye-otel` locally; the code only uses the API.

## Testing

Tests live in @apps/hook-eye/tests, with each check's tests in its own directory (e.g.
`tests/unit/ccr/`), and run with `moon run hook-eye:unit-test`, or manually
with `MERINO_HOOK_EYE_ENV=testing uv run pytest apps/hook-eye/tests/unit/ --no-cov`.
