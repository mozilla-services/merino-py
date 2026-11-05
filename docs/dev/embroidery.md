# Embroidery: local development

Embroidery is Mozilla's image service, a Rust service in `apps/embroidery`. It replaces the
Navigational Suggestions job: it stores entities, fetches their favicons and logos, and serves them
to Firefox.

## Prerequisites

- [rustup](https://rustup.rs). The first Cargo command in `apps/embroidery` installs the
  toolchain pinned in `rust-toolchain.toml`.
- Moon, as described in [Working in the monorepo](./monorepo.md).

## Run the service

```bash
cd apps/embroidery
cargo run -- serve
curl -i localhost:8000/__heartbeat__
```

`EMBROIDERY_ENV` defaults to `development`, which binds `127.0.0.1:8000` and logs
human-readable lines. To see the MozLog JSON that deployments emit:

```bash
EMBROIDERY_LOGGING__FORMAT=mozlog cargo run -- serve
```

## Configuration

Later sources override earlier ones:

| Source | Example |
| --- | --- |
| `configs/default.toml`, embedded in the binary | `[server] port = 8000` |
| `configs/${EMBROIDERY_ENV}.toml`, embedded | `development.toml`, `production.toml` |
| `configs/${EMBROIDERY_ENV}.local.toml`, optional, gitignored | your overrides |
| `EMBROIDERY_SECTION__KEY` environment variables | `EMBROIDERY_SERVER__PORT=9000` |

`EMBROIDERY_ENV` accepts `development`, `testing`, `stage` and `production`. The service fails
at startup with the offending key when a value is invalid or a section contains an unknown key.
`configs/default.toml` documents every setting.

## Endpoints

| Route | Response |
| --- | --- |
| `GET /__lbheartbeat__` | 200, empty. Liveness, checks no backend. |
| `GET /__heartbeat__` | 200 with `{"status":"ok","checks":{}}`. Readiness. |
| `GET /__version__` | The contents of `version_file`, or 500 if it's missing. |

## Checks

From the repository root:

```bash
moon run embroidery:format-check embroidery:lint embroidery:test
```

`moon run :lint` and `moon run :test` include Embroidery alongside the Python projects.
