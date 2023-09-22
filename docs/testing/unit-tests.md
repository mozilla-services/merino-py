# Unit Tests

The unit layer is suitable for testing complex behavior at a small scale, with fine-grained control over the inputs.
Due to their narrow scope, unit tests are fundamental to thorough test coverage.

To execute unit tests, use: `make unit-tests`

Unit tests are written and executed with pytest and are located in the `tests/unit` directory,
using the same organizational structure as the source code of the merino service.
Type aliases dedicated for test should be stored in the `types.py` module.
The `conftest.py` modules contain common utilities in fixtures.

For a breakdown of fixtures in use per test, use: `make unit-test-fixtures`

## Fixtures

Available fixtures include:

### FilterCaplogFixture
Useful when verifying log messages, this fixture filters log records captured with
pytest's caplog by a given `logger_name`.

_**Usage:**_
```python
def test_with_filter_caplog(
    caplog: LogCaptureFixture, filter_caplog: FilterCaplogFixture
) -> None:
    records: list[LogRecord] = filter_caplog(caplog.records, "merino.providers.adm")
```
Note: This fixture is shared with integration tests.

### SuggestionRequestFixture
For use when querying providers, this fixture creates a SuggestionRequest object with
a given `query`

_**Usage:**_
```python
def test_with_suggestion_request(srequest: SuggestionRequestFixture) -> None:
    request: SuggestionRequest = srequest("example")
    result: list[BaseSuggestion] = await provider.query(request)
```

### ScopeFixture, ReceiveMockFixture & SendMockFixture
For use when testing middleware, these fixtures initialize or mock the common Scope,
Receive and Send object dependencies.

_**Usage:**_
```python
def test_middleware(scope: Scope, receive_mock: Receive, send_mock: Send) -> None:
    pass
````