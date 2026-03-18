---
name: review-provider
description: Review a Merino suggest provider implementation against codebase patterns and best practices
---

# Review a Suggest Provider

Review the provider specified in $ARGUMENTS against Merino's patterns and best practices. If no provider is specified, ask which provider to review.

## Step 1: Read the provider implementation

Read all files in `merino/providers/suggest/{provider_name}/` including:
- `provider.py`
- `backends/protocol.py` (if exists)
- All backend implementations
- Any other files in the directory

Also read the provider's registration in `merino/providers/suggest/manager.py` (find the matching `ProviderType` and `case` block).

Read the provider's config section in `merino/configs/app_configs/default.toml`.

Read tests in `tests/unit/providers/suggest/{provider_name}/` and `tests/integration/providers/suggest/{provider_name}/`.

## Step 2: Check against patterns

Review each of these areas and report findings. For each area, state PASS, WARN, or FAIL with an explanation.

### Provider Class Structure
- [ ] Class is named `Provider` and extends `BaseProvider`
- [ ] `__init__` stores `self._name`, `self._enabled_by_default`, `self._query_timeout_sec`
- [ ] `__init__` calls `super().__init__()` (at end, without arguments, or with `**kwargs`)
- [ ] `initialize()` is async
- [ ] `query()` returns `list[BaseSuggestion]`
- [ ] `shutdown()` is implemented (even if no-op)
- [ ] `logger = logging.getLogger(__name__)` at module level

### Error Handling
- [ ] `query()` catches backend errors and returns `[]` instead of crashing
- [ ] Errors are logged at `warning` level (not `error` unless truly fatal)
- [ ] If calling external APIs: does it need a circuit breaker? (check if Weather/FlightAware pattern applies)
- [ ] No bare `except:` clauses (should catch specific exceptions)

### Query Normalization
- [ ] `normalize_query()` is implemented if the provider uses keyword matching
- [ ] At minimum strips whitespace and lowercases

### Metrics
- [ ] Uses `metrics_client` for timing external calls (e.g., `self.metrics_client.timeit(...)`)
- [ ] Provider-level metrics are tracked

### Caching (if applicable)
- [ ] Uses `RedisAdapter` / `NoCacheAdapter` pattern from manager
- [ ] Cache TTLs are configurable via settings

### Configuration
- [ ] Provider section exists in `default.toml` with `type`, `backend`, `enabled_by_default`, `score`, `query_timeout_sec`
- [ ] API keys/URLs in separate section (not under `providers.*`)
- [ ] Registered in `ProviderType` enum
- [ ] Has a `case` in `_create_provider()` factory

### Custom Details
- [ ] If returning extra fields: uses `CustomDetails` pattern (not top-level fields on `BaseSuggestion`)
- [ ] Details model defined in `custom_details.py`

### Backend Protocol (if applicable)
- [ ] Backend interface defined as a `Protocol` class
- [ ] Fake backend exists for testing
- [ ] Backend methods raise `BackendError` subclass on failures

### Testing
- [ ] Unit tests exist for the provider
- [ ] Tests cover: initialization, happy path query, error handling, query normalization
- [ ] Backend mocked with `mocker.AsyncMock(spec=BackendProtocol)`
- [ ] All async tests have `@pytest.mark.asyncio`
- [ ] Tests use fixtures from conftest, not inline setup

### Data Refresh (if applicable)
- [ ] Uses `merino/utils/cron.py` `Job` class for periodic refresh
- [ ] Cron task created with `asyncio.create_task()` in `initialize()`
- [ ] Has a `_should_fetch()` condition function
- [ ] Handles fetch failures gracefully (logs, doesn't crash)

## Step 3: Report

Present findings as a checklist with PASS/WARN/FAIL for each area. Include:
- A summary of the provider's health (good / needs attention / significant issues)
- Specific actionable recommendations for any WARN or FAIL items
- Code snippets showing exactly what to fix, referencing existing providers as examples
