# Merino-py

Mozilla's suggestion service for Firefox. Privacy-preserving buffer between Firefox's address bar and third-party providers.

Three subsystems: **Suggest API** (FastAPI, `merino/providers/suggest/`), **Curated Recommendations** (NewTab, `merino/curated_recommendations/`), **Jobs** (Airflow pipelines, `merino/jobs/`).

## Commands

```bash
make install              # Install deps (uv sync --all-groups)
make dev                  # FastAPI dev server with hot-reload
make test                 # Unit + integration tests (95% coverage enforced)
make lint                 # ruff + bandit + mypy
make format               # Auto-format with ruff
make docker-compose-up    # Start local services (Redis, fake-GCS)
```

Run tests manually: `MERINO_ENV=testing uv run pytest tests/unit/`

Run jobs: `uv run merino-jobs --help` (e.g. `uv run merino-jobs wikipedia-indexer index`)

## Critical Gotchas

- **MERINO_ENV=testing** must be set when running tests. Without it, development config loads and tests break. All Makefile test targets set this automatically.
- **Python 3.13 only**. Pinned in `.python-version`.
- **Line length is 99**, not 88 or 120.
- **Warnings are errors** in tests (`filterwarnings = ["error"]`). Any warning from code or deps fails the test.
- **95% code coverage** required. New code without tests fails CI.
- **Docstrings required** on all public functions/classes (D212 convention). Exceptions: `__init__` and magic methods.
- **Pre-commit auto-fixes then fails**: ruff runs with `--exit-non-zero-on-fix`. Re-stage and commit again.
- **Strict mypy**: `disallow_untyped_calls`, `warn_return_any`, `warn_unused_ignores` are all enabled.
- **Async tests** need `@pytest.mark.asyncio` or they silently don't run.

## Coding Conventions (deviations from defaults)

- **Type unions**: `X | None` not `Optional[X]`. `list[str]` not `List[str]`.
- **Async concurrency**: Use `merino/utils/task_runner.py` (custom gather with timeout), NOT raw `asyncio.gather()`.
- **Logging**: `logger = logging.getLogger(__name__)`. Use `extra={}` for structured context.
- **Error handling**: Providers catch `BackendError`, log warning, return `[]`. Never crash the request.
- **Pydantic fields**: Use `Field(description="...")`. Use `SerializeAsAny[BaseSuggestion]` for polymorphic serialization.
- **Imports**: stdlib -> third-party -> local, separated by blank lines.

## Configuration

Dynaconf with TOML files in `merino/configs/app_configs/`. Switched by `MERINO_ENV` (development/testing/ci/stage/production).

Env var overrides: `MERINO_{SECTION}__{KEY}=value` (double underscore for nesting).

Access in code: `from merino.configs import settings`

No `.env` files exist. All config is TOML + env vars.
