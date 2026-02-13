---
paths:
  - "merino/providers/**"
  - "tests/**/providers/**"
---

# How to Add a New Suggest Provider

## Files to create

```
merino/providers/suggest/myprovider/
├── __init__.py
├── provider.py                 # Provider class extending BaseProvider
└── backends/
    ├── __init__.py
    ├── protocol.py             # Backend Protocol interface
    ├── real_backend.py         # Real implementation
    └── fake_backend.py         # Fake for testing
```

## Steps

1. **Backend protocol** (`backends/protocol.py`): Define a `Protocol` class with async methods.

2. **Backend implementations**: Real backend (API calls, cache) and fake backend (returns test data).

3. **Provider class** (`provider.py`): Extend `BaseProvider`. Implement `initialize()`, `query()`, `shutdown()`. Use `self._name`, `self._query_timeout_sec`, `self._enabled_by_default` for base properties.

4. **Custom details** (if returning extra fields): Edit `merino/providers/suggest/custom_details.py`. Add a details model class and an optional field on `CustomDetails`.

5. **Register in manager** (`merino/providers/suggest/manager.py`):
   - Add to `ProviderType` enum
   - Add case in `_create_provider()` factory

6. **Configuration** (`merino/configs/app_configs/default.toml`):
   - Add `[default.providers.myprovider]` with `type`, `backend`, `enabled_by_default`, `score`, `query_timeout_sec`
   - Add `[default.myprovider]` for API keys/URLs if needed

7. **Tests**:
   - `tests/unit/providers/suggest/myprovider/test_provider.py`
   - `tests/unit/providers/suggest/myprovider/backends/test_*.py`
   - Mock backends with `mocker.AsyncMock(spec=MyBackend)`

No changes needed to routes - providers are auto-discovered from config.

## Reference implementations

- **Simple**: `merino/providers/suggest/geolocation/` (no backend, no caching)
- **With caching + circuit breaker**: `merino/providers/suggest/weather/`
- **With GCS manifest + cron**: `merino/providers/suggest/finance/`
