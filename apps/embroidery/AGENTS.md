# Embroidery

A Rust web service (Axum, Tower, Tokio, sqlx, tracing) that stores entities, fetches their favicons
and logos, and serves them to Firefox. One binary, one image: `embroidery serve` runs the API,
the other subcommands run as CronJobs and Jobs.

## Architecture

- Layers: `src/api/` (HTTP), `src/jobs/` (batch commands), `src/catalog/` (shared writes),
  `src/infra/` (PostgreSQL, GCS, outbound HTTP), `src/scraper/`, `src/domain/`.
- `api` and `jobs` call `catalog`, which uses `infra`. All of them may use `domain`.
- `src/domain/` never imports axum, sqlx, reqwest or `google_cloud_*`.
- Handlers are thin: extract request data, call `catalog`, return a response. No SQL, no business
  logic.
- Shared state lives in `AppState` and is extracted with `State<AppState>`.
- `main.rs` only parses the CLI, loads config, starts telemetry, dispatches and maps errors to an
  exit code. CronJobs read that exit code.

## Errors

- `thiserror` enums in `domain`, `config` and `api`. `anyhow` only in `cli`, `main` and
  `AppError::Internal`.
- Every handler returns `AppResult<T>`. No `unwrap()` or `expect()` in request-handling code.
- `AppError::Internal` logs the full chain and returns a generic message. Never put paths, SQL or
  upstream responses in a response body.
- Report an error once, at the boundary that owns the response or the exit code.

## Data

- All SQL lives in `src/infra/db/`, as `sqlx::query!`/`query_as!` with committed `.sqlx/` metadata.
- Parameterized queries only. Convert rows to domain types with `TryFrom`, not `From`.
- Separate types at boundaries: request DTOs, domain types, database rows, response DTOs.

## Configuration and logging

- Config: `configs/default.toml`, then `configs/${EMBROIDERY_ENV}.toml` (both embedded), then
  `configs/${env}.local.toml` (gitignored), then `EMBROIDERY_SECTION__KEY` variables.
- Add new settings to `default.toml` with a comment, and to the typed structs in `src/config.rs`.
  Sections use `deny_unknown_fields`; the top level must not (Kubernetes service links).
- Secrets are `secrecy::SecretString`. Never log them.
- Logs are MozLog JSON in deployments (`src/telemetry/mozlog.rs`). Use structured fields, not
  formatted strings: `tracing::info!(entity = %uri, "fetched")`.

## Testing

- Unit tests next to the code. Router tests through `router(state, timeout)` with
  `tower::ServiceExt::oneshot`.
- Test error paths, not just happy paths.
- Tests never mutate the process environment (it's `unsafe` in edition 2024 and `unsafe_code` is
  forbidden). Pass explicit inputs, as `Config::load_from` does.
- Review new `insta` snapshots before committing them.

## Verification

A change is done when all of these pass, from the repository root:

```
moon run embroidery:format-check embroidery:lint embroidery:test
```

Clippy warnings fail CI. Fix them rather than adding `allow`; when an exception is justified, use
`#[expect(..., reason = "...")]`.
