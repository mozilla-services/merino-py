# Testing strategies

There are four major testing strategies used in this repository: unit tests,
Python integration tests, Python contract tests, and Python load tests.

Test code resides in the [tests][tests] directory and [test-engineering][test-engineering]
directories.

## Unit Tests

Unit tests should appear close to the code they are testing, using standard Rust
unit tests. This is suitable for testing complex behavior at a small scale, with
fine grained control over the inputs.

## Contract tests

The tests in the `test-engineering/contract-tests` directory are contract tests
that consume Merino's APIs using more opaque techniques. These tests run against
a Docker container of the service, specify settings via environment variables,
and operate on the HTTP API layer only and as such are more concerned with
external contracts and behavior. The contract tests cannot configure the server
per test.

For more details see the README.md file in the `test-engineering/contract-tests`
directory.

## Load tests

The tests in the `test-engineering/load-tests` directory are load tests that
spawn multiple HTTP clients that consume Merino's API. These tests do not run on
CI. We run them manually to simulate real-world load on the Merino infrastructure.

[tests]: ../../tests/
[test-engineering]: ../../test-engineering/
