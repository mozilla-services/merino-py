# Testing strategies

Merino is tested using a four tier strategy composed of unit, integration, contract
and load level testing.

Test code resides in the `tests` directory.

## Unit Tests

The unit layer is suitable for testing complex behavior at a small scale, with fine
grained control over the inputs. Due to their narrow scope, unit tests are fundamental
to thorough test coverage.

Unit tests are written and executed with pytest and are located in the `tests/unit`
directory, using the same organizational structure as the source code of the merino
service.
## Integration Tests

The integration layer of testing allows for verification of interactions between
service components, with lower development, maintenance and execution costs compared
with higher level tests, such as contract tests.

Integration tests are located in the `tests/integration` directory. They use pytest and
the FastAPI `TestClient` to send requests to specific merino endpoints and verify
responses as well as other outputs, such as logs. Tests are organized according to the
API path under test.

## Contract tests

The tests in the `tests/contract` directory are contract tests
that consume Merino's APIs using more opaque techniques. These tests run against
a Docker container of the service, specify settings via environment variables,
and operate on the HTTP API layer only and as such are more concerned with
external contracts and behavior. The contract tests cannot configure the server
per test.

For more details see the README.md file in the `test/contract`
directory.

## Load tests

The tests in the `tests/load` directory are load tests that
spawn multiple HTTP clients that consume Merino's API. These tests do not run on
CI. We run them manually to simulate real-world load on the Merino infrastructure.
