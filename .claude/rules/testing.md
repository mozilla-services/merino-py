---
paths:
  - "apps/merino/tests/**"
---

# Testing Conventions

## Running tests

```bash
moon run merino:test                         # Unit + integration + 95% coverage (needs Docker)
moon run merino:unit-test                    # Unit only
moon run merino:integration-test             # Integration only (needs Docker)
moon run merino:diff-coverage                # Both + coverage check
moon run merino:unit-test -- -k weather      # Tests matching keyword

# Manual pytest runs MUST set MERINO_ENV (moon tasks do this automatically):
MERINO_ENV=testing uv run pytest apps/merino/tests/unit/path/to/test.py -v
```

## Key fixtures

- `statsd_mock` (apps/merino/tests/conftest.py) - Mock StatsD client
- `srequest` (apps/merino/tests/unit/conftest.py, session scope) - Factory for `SuggestionRequest` objects
- `gcs_bucket_mock`, `gcs_blob_mock` (apps/merino/tests/unit/conftest.py, **autouse**) - Auto-applied to all unit tests
- `filter_caplog` (apps/merino/tests/conftest.py) - Filter log records by logger name

## Mocking patterns

```python
# Mock a provider backend
backend_mock = mocker.AsyncMock(spec=MyBackend)
backend_mock.fetch.return_value = expected_data

# Mock settings
mocker.patch.dict(settings.providers, values={...})

# Assert on logs
records = filter_caplog(caplog.records, "merino.providers.suggest.myprovider")
assert len(records) == 1
```

## Integration tests

Use `testcontainers` for Docker-based services (Redis, GCS). Fixtures in `apps/merino/tests/integration/fixtures/`. Provider injection in API tests uses FastAPI dependency overrides:

```python
app.dependency_overrides[get_providers] = get_provider_factory(mock_providers)
```

## Rules

- All async test functions need `@pytest.mark.asyncio`
- Use `pytest.mark.parametrize` with `ids=` for readable test output
- Warnings are errors - any warning fails the test
- 95% coverage minimum enforced in CI
