# Integration Tests

The integration layer of testing allows for verification of interactions between service components,
with lower development, maintenance and execution costs compared with higher level tests, such as contract tests.

To execute integration tests, use: `make integration-tests`

Integration tests are located in the `tests/integration` directory.
They use pytest and the FastAPI `TestClient` to send requests to specific merino endpoints and verify responses as well as other outputs, such as logs.
Tests are organized according to the API path under test.
Type aliases dedicated for test should be stored in the `types.py` module.
Fake providers created for test should be stored in the `fake_providers.py` module.
The `conftest.py` modules contain common utilities in fixtures.

For a breakdown of fixtures in use per test, use: `make integration-test-fixtures`

## Fixtures

Available fixtures include:

### FilterCaplogFixture

[Details](#FilterCaplogFixture) available in Unit Tests section

### TestClientFixture
This fixture creates an instance of the TestClient to be used in testing API calls.

_**Usage:**_
```python
def test_with_test_client(client: TestClient):
    response: Response = client.get("/api/v1/endpoint")
```

### TestClientWithEventsFixture
This fixture creates an instance of the TestClient, that will trigger event handlers
(i.e. `startup` and `shutdown`) to be used in testing API calls.

_**Usage:**_
```python
def test_with_test_client_with_event(client_with_events: TestClient):
    response: Response = client_with_events.get("/api/v1/endpoint")
```

### RequestSummaryLogDataFixture
This fixture will extract the extra log data from a captured 'request.summary'
LogRecord for verification

_**Usage:**_
```python
def test_with_log_data(
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
    extract_request_summary_log_data: LogDataFixture
):
    records: list[LogRecord] = filter_caplog(caplog.records, "request.summary")
    assert len(records) == 1

    record: LogRecord = records[0]
    log_data: dict[str, Any] = extract_request_summary_log_data(record)
    assert log_data == expected_log_data
```

### InjectProvidersFixture & ProvidersFixture
These fixture will setup and teardown given providers.

_**Usage:**_

If specifying providers for a module:
```python
@pytest.fixture(name="providers")
def fixture_providers() -> Providers:
    return {"test-provider": TestProvider()}
```

If specifying providers for a test:
```python
@pytest.mark.parametrize("providers", [{"test-provider": TestProvider()}])
def test_with_provider() -> None:
    pass
```

### SetupProvidersFixture
This fixture sets application provider dependency overrides.

_**Usage:**_
```python
def test_with_setup_providers(setup_providers: SetupProvidersFixture):
    providers: dict[str, BaseProvider] = {"test-provider": TestProvider()}
    setup_providers(providers)
```

### TeardownProvidersFixture
This fixture resets application provider dependency overrides and is often used in
teardown fixtures.

_**Usage:**_
```python
@pytest.fixture(autouse=True)
def teardown(teardown_providers: TeardownProvidersFixture):
    yield
    teardown_providers()
```