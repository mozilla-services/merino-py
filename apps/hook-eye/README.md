# Hook-eye: additional monitoring for Merino

Most of Merino's observability and monitoring needs are met by application-level metrics,
traces, and OpenTelemetry Collector receivers. However, some processes can't be monitored by
these existing methods. Hook-eye is a small service to fill that gap.

A check belongs in hook-eye when:

- it can't come from Merino's own metrics or an existing OpenTelemetry Collector receiver;
- it polls a single shared resource, where one poller is correct and one per Merino pod would
  multiply load and duplicate series;
- or it needs privileges that Merino's pods shouldn't have.

Hook-eye runs as its own single-replica deployment, so each check reports one set of series.
Extra replicas report duplicates.

Currently, it monitors cross-cluster replication (CCR) in Merino's follower Elasticsearch
clusters. `GET _ccr/stats` isn't covered by the Elasticsearch receiver, needs the `monitor`
cluster privilege that Merino's pods lack, and only needs one reader per follower.

The project name "hook-eye" is a play on the hook-and-eye fastener, which keeps two pieces of
fabric joined, in the spirit of "[merino](https://github.com/mozilla-services/merino-py/#about-the-name)"
and "fleece".

See [metrics.yaml](./metrics.yaml) for the metrics it emits, and
[docs/dev/hook-eye.md](../../docs/dev/hook-eye.md) for configuration, local verification
recipes, and example queries.

## Quick start (CCR monitor)

Run these from the repository root.

```sh
make install                  # once
make docker-compose-up-ccr    # leader (:9200), follower (:9201), OpenTelemetry stack
make dev-hook-eye             # scrape the follower every 15s and log each scrape
curl -i localhost:8002/__heartbeat__
```

Auto-follow only picks up indices created after the pattern exists, so create one on the
leader before expecting per-shard metrics:

```sh
curl -X PUT "http://localhost:9200/enwiki-local-1"
curl "http://localhost:9201/_ccr/stats?pretty"   # the follower has picked it up
```

To export metrics to the local collector instead (Prometheus at <http://localhost:9090>,
Grafana at <http://localhost:3000>), run `make dev-hook-eye-otel`. Without it, the
OpenTelemetry instruments are no-ops.

Point at a different follower with `MERINO_HOOK_EYE_CCR_FOLLOWER__URL` and
`MERINO_HOOK_EYE_CCR_FOLLOWER__API_KEY`, or turn the check off with
`MERINO_HOOK_EYE_CCR_FOLLOWER__ENABLED=false`. Settings live in
[merino_hook_eye/configs](./merino_hook_eye/configs) and are selected by `MERINO_HOOK_EYE_ENV`.

## Testing

```sh
moon run hook-eye:unit-test       # unit tests with coverage (sets MERINO_HOOK_EYE_ENV=testing)
moon run hook-eye:lint hook-eye:format-check hook-eye:typecheck hook-eye:security
moon run hook-eye:docker-build    # builds app-hook-eye:build
```

To run the tests without moon, set the environment yourself:

```sh
MERINO_HOOK_EYE_ENV=testing uv run pytest apps/hook-eye/tests/unit/ --no-cov
```

There's no integration suite yet; `integration-test` is excluded in [moon.yml](./moon.yml).
