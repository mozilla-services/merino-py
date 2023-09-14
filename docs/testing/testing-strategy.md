# Test Strategy

Merino is tested using a combination of functional and performance tests.

Test code resides in the `tests` directory.

Merino's test strategy requires that we do not go below a minimum test coverage percentage for unit and integration tests.
All Contract tests must pass and load tests cannot go below a minimum performance threshold.

Test documentation resides in the [/docs/testing/][test_docs_dir] directory.

The functional test strategy is four-tiered, composed of: 

- [unit][unit_tests] - [documentation][unit_tests_docs]
- [integration][integration_tests] - [documentation][integration_tests_docs]
- [contract][contract_tests] - [documentation][contract_tests_docs]
- [load][load_tests] - [documentation][load_tests_docs]

See documentation and repositories in each given test area for specific details on running and maintaining tests.

[test_dir]: /tests/
[test_docs_dir]: /docs/testing/
[unit_tests]: /tests/unit/
[unit_tests_docs]: /docs/testing/unit-tests.md
[integration_tests]: /tests/integration/
[integration_tests_docs]: /docs/testing/integration-tests.md
[contract_tests]: /tests/contract/
[contract_tests_docs]: /docs/testing/contract-tests/
[load_tests]: /tests/load/
[load_tests_docs]: /docs/testing/load-tests.md