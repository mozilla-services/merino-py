# merino-fleece PII Detection (Prototype)

Merino can route a fraction of suggest traffic through
[merino-fleece](../merino-fleece/README.md), a separate service that performs
spaCy-backed PII (named-entity) detection on search terms. When a query is
flagged, Merino **suppresses its suggestions and excludes it from logging**. This
is a prototype, gated behind a feature flag.

## Two independent gates

The feature only runs when **both** of these are true:

1. **`fleece.url_base` is configured** — the address of the merino-fleece service.
   Empty by default, which leaves the feature off and the client uninitialized
   (`get_fleece_client()` returns `None`). It is injected per environment through
   `MERINO_FLEECE__URL_BASE` (e.g. `http://localhost:8000` for local dev).
2. **The `fleece-pii-detection` feature flag is enabled** — see
   [Feature Flags](./dev/feature_flags.md). It uses the `random` scheme, so `enabled`
   is the fraction of total traffic the check applies to.

## Request flow

In the suggest endpoint (`merino/web/api_v1.py`):

1. The existing regex `pii_inspect(q)` runs first. An email short-circuits and
   returns empty suggestions immediately, so emails are never sent to fleece.
2. If the flag is on and the fleece client is configured, Merino awaits the fleece
   check **before building the provider lookups**. If fleece reports PII, the
   request's `PIIType` is set to `PERSON` (which the logging middleware treats as
   sensitive, suppressing the log line) and an empty suggestion response is
   returned — so a flagged query is never sent to the downstream providers.


## Fail-open

If merino-fleece times out, is unreachable, or returns an unexpected response, the
client logs a warning, emits `fleece.pii.error`, and returns `False`. The suggest
request then proceeds normally.

## Metrics

| Metric | Type | Notes |
| --- | --- | --- |
| `fleece.pii.detect_duration` | timing | How long the merino-fleece PII check took to respond. |
| `fleece.pii.error` | counter | Tagged `reason` (`http` / `response`); fail-open. |
| `suggestions.query.pii_detected` | counter | Tagged `type=person` when fleece suppresses a query |

## Configuration

`[default.fleece]` in `merino/configs/default.toml`:

- `url_base` — fleece base URL; empty disables the feature.
- `pii_path` — endpoint path (`/api/v1/pii`).
- `connect_timeout_sec` / `request_timeout_sec` — kept short so that a slow
  merino-fleece response does not delay Merino's reply to the user. On timeout the
  check fails open (the query is treated as non-PII and proceeds normally).
