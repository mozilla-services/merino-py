---
name: new-provider
description: Scaffold a new Merino suggest provider with all required files, registration, config, and tests
---

# Scaffold a New Suggest Provider

You are scaffolding a new provider for the Merino suggest API. Follow this process exactly.

## Step 1: Interview the user

Use the AskUserQuestion tool to ask ALL of these questions at once (combine into a single AskUserQuestion call with multiple questions):

1. **Provider name** (snake_case, e.g. "movie_db"): What should the provider be called? This will be used for directory names, config keys, and the ProviderType enum.

2. **Backend type**: Does this provider need an external API backend?
   - "Yes - external API" (needs backend protocol, real + fake implementations, API config). A **fake backend** is a lightweight concrete class implementing the backend protocol that returns empty/hardcoded data. It serves as the default when the real API is not configured. This follows the codebase convention (`FakeWeatherBackend`, `FakeAdmBackend`, etc.) and is distinct from a mock (which uses `unittest.mock` to record and assert on calls).
   - "No - self-contained" (like geolocation, no external calls)

3. **Caching**: Does this provider need Redis caching?
   - "Yes - Redis cache" (adds RedisAdapter setup in manager, cache config)
   - "No caching"

4. **Custom details**: Does this provider return custom fields beyond title/url/icon/score?
   - "Yes - has custom fields" (will create a details model in custom_details.py)
   - "No - standard fields only"

Wait for answers before proceeding.

## Step 2: Ask follow-up questions based on answers

If the provider has an external API backend, ask:
- What is the external API called? Provide the human-readable name (e.g., "Polygon", "TMDB"). This will be used to derive PascalCase class names (`PolygonBackend`) and lowercase file/directory names (`polygon/`).
- Does it need a circuit breaker for resilience? (like Weather/FlightAware providers)
- Does it need periodic background data refresh via cron? (like Finance/ADM/Weather providers)

If the provider has custom details, ask:
- What custom fields should the details model have? (e.g. "rating: float, genre: str")

Wait for answers before proceeding.

## Step 3: Create all files

Create the following files. Follow these specific conventions from existing providers: class naming, module-level logger, `__init__` parameter ordering (provider-specific params first, `**kwargs: Any` last), import conventions, error handling in `query()`, and protocol compliance.

### Naming conventions

All derived names follow from the provider's `snake_case` name (`{name}`) and its `PascalCase` form (`{Name}`).

`{Name}` = PascalCase derived by splitting on `_` and capitalizing each part: `movie_db` → `MovieDb`, `top_picks` → `TopPicks`.

| Concept | Format | Example (`movie_db` / `TMDB`) |
|---------|--------|-------------------------------|
| Directory | `suggest/{name}/` | `suggest/movie_db/` |
| Provider class | always `Provider` | `class Provider(BaseProvider)` |
| Import alias | `{Name}Provider` | `MovieDbProvider` |
| Backend protocol | `{Name}Backend` | `MovieDbBackend(Protocol)` |
| Error class | `{Name}BackendError` | `MovieDbBackendError` |
| Fake backend | `Fake{Name}Backend` | `FakeMovieDbBackend` |
| Enum entry | `{NAME_UPPER} = "{name}"` | `MOVIE_DB = "movie_db"` |

### 3a. Provider directory structure

Create `merino/providers/suggest/{name}/__init__.py` (empty or with docstring).

### 3b. Backend protocol (if external API)

Create `merino/providers/suggest/{name}/backends/__init__.py` (empty).

Create `merino/providers/suggest/{name}/backends/protocol.py`:
```python
"""Protocol for {name} provider backends."""

from typing import Protocol

from pydantic import BaseModel

from merino.exceptions import BackendError


class {Name}BackendError(BackendError):
    """{Name}-specific errors."""

    pass


# Add data models here based on what the API returns


class {Name}Backend(Protocol):
    """Protocol for the {name} backend."""

    async def search(self, query: str) -> list[...]:
        """Search the backend."""
        ...

    async def shutdown(self) -> None:
        """Close connections."""
        ...
```

### 3c. Fake backend (if external API)

The fake backend is the default used in `_create_provider()`'s `else` branch when the real API is not configured (e.g., missing API key or `setting.backend` doesn't match the real backend name). See `FakeWeatherBackend` in `weather/backends/fake_backends.py`, `FakeWikipediaBackend` in `wikipedia/backends/fake_backends.py`, and `FakeAdmBackend` in `adm/backends/fake_backends.py` for existing examples.

Create `merino/providers/suggest/{name}/backends/fake_backends.py`:
```python
"""Fake backends for testing."""

from merino.providers.suggest.{name}.backends.protocol import {Name}Backend


class Fake{Name}Backend:
    """Fake {name} backend for testing."""

    async def search(self, query: str) -> list:
        """Return empty results."""
        return []

    async def shutdown(self) -> None:
        """No-op shutdown."""
        pass
```

### 3d. Real backend (if external API)

Create `merino/providers/suggest/{name}/backends/{api_name_lower}.py` with the real implementation. Follow the pattern from `merino/providers/suggest/finance/backends/polygon/backend.py`.

### 3e. Provider class

Create `merino/providers/suggest/{name}/provider.py`. Follow these exact patterns:

- Class must be named `Provider` and extend `BaseProvider`
- Store `self._name`, `self._query_timeout_sec`, `self._enabled_by_default` in `__init__`
- Accept `**kwargs: Any` as the last `__init__` parameter, call `super().__init__(**kwargs)` at the end. This is the pattern used by the majority of providers (weather, wikipedia, geolocation, amo, top_picks, adm).
- `initialize()` must be async, set up cron jobs if needed with `asyncio.create_task(cron_job())`
- `query()` must return `list[BaseSuggestion]`. Wrap backend calls in `try`/`except` catching the provider's `{Name}BackendError` (or the base `BackendError`), log at `warning` level, and return `[]`. See `wikipedia/provider.py:80-88` and `amo/provider.py:118-133` for the standard pattern. Note: providers with circuit breakers (weather, flightaware) intentionally let errors propagate so the breaker can track failures.
- `normalize_query()` should at minimum do `query.lower().strip()`
- Add `logger = logging.getLogger(__name__)` at module level
- If using circuit breaker, decorate `query()` with the circuit breaker

Reference implementations:
- Simple: `merino/providers/suggest/geolocation/provider.py`
- With backend + cron: `merino/providers/suggest/finance/provider.py`
- With circuit breaker: `merino/providers/suggest/weather/provider.py`

### 3f. Custom details (if needed)

Edit `merino/providers/suggest/custom_details.py`:
1. Add a new details model class (e.g. `class {Name}Details(BaseModel):`)
2. Add it as an optional field on `CustomDetails`: `{name}: {Name}Details | None = None`
3. Add the import at the top of the file

### 3g. Register in manager

Edit `merino/providers/suggest/manager.py`:
1. Add import for the Provider class: `from merino.providers.suggest.{name}.provider import Provider as {Name}Provider`
2. If external API, add imports for backend classes
3. Add entry to `ProviderType` enum: `{NAME_UPPER} = "{name}"`
4. Add a new `case ProviderType.{NAME_UPPER}:` block in `_create_provider()`. Follow the pattern of existing providers:
   - If Redis cache: create `RedisAdapter` or `NoCacheAdapter` based on `setting.cache`
   - Instantiate backend (real if `setting.backend == "{api_name}"`, else fake)
   - Instantiate provider with `metrics_client=get_metrics_client()`, `score=setting.score`, `name=provider_id`, `query_timeout_sec=setting.query_timeout_sec`, `enabled_by_default=setting.enabled_by_default`

### 3h. Configuration

Edit `merino/configs/app_configs/default.toml`. Add:
```toml
[default.providers.{name}]
type = "{name}"
backend = "{api_name_lower}"
enabled_by_default = false
score = 0.25
query_timeout_sec = 5.0
cache = "none"
```

If external API, also add:
```toml
[default.{name}]
api_key = ""
url_base = ""
```

### 3i. Test files

Create `tests/unit/providers/suggest/{name}/__init__.py` (empty).

Create `tests/unit/providers/suggest/{name}/conftest.py` with fixtures:
- `backend_mock` fixture using `mocker.AsyncMock(spec={Name}Backend)`
- `provider` fixture creating the Provider instance

Create `tests/unit/providers/suggest/{name}/test_provider.py` with tests:
- `test_initialize` - tests async initialization
- `test_query_returns_suggestions` - tests happy path
- `test_query_returns_empty_on_error` - tests error handling
- `test_normalize_query` - tests query normalization
- All async tests use `@pytest.mark.asyncio`

If external API, create `tests/unit/providers/suggest/{name}/backends/__init__.py` and test files.

## Step 4: Verify

After creating all files:
1. Run `MERINO_ENV=testing uv run pytest tests/unit/providers/suggest/{name}/ -v` to verify tests pass
2. Run `uv run ruff check merino/providers/suggest/{name}/` to verify linting passes
3. Run `uv run mypy merino/providers/suggest/{name}/` to verify type checking passes

Report the results and any issues to the user.
