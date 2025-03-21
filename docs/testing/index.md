
# Merino Testing

## Test Strategy

Merino is tested using a combination of functional and performance tests.

Test code resides in the `tests` directory.

Merino's test strategy requires that we do not go below a minimum test coverage percentage for unit
and integration tests. Load tests cannot go below a minimum performance threshold.

Functional tests push test artifacts, in the form of JUnit XMLs and Coverage JSONs to the 
[ETE Test Metric Pipeline][ete_pipeline] for trending and monitoring. Results can be found on the 
[Merino-py Test Metrics Looker Dashboard][looker_dashboard].

Test documentation resides in the [/docs/testing/][test_docs_dir] directory.

The test strategy is three-tiered, composed of:

- [unit][unit_tests] - [documentation][unit_tests_docs]
- [integration][integration_tests] - [documentation][integration_tests_docs]
- [load][load_tests] - [documentation][load_tests_docs]

See documentation and repositories in each given test area for specific details on running and
maintaining tests.

[ete_pipeline]: https://mozilla.github.io/ecosystem-test-scripts/introduction.html
[integration_tests]: https://github.com/mozilla-services/merino-py/tree/main/tests/integration
[integration_tests_docs]: ./integration-tests.md
[load_tests]: https://github.com/mozilla-services/merino-py/tree/main/tests/load
[load_tests_docs]: ./load-tests.md
[looker_dashboard]: https://mozilla.cloud.looker.com/dashboards/1976?Timestamp+Date=365+day
[unit_tests]: https://github.com/mozilla-services/merino-py/tree/main/tests/unit
[unit_tests_docs]: ./unit-tests.md
[test_dir]: https://github.com/mozilla-services/merino-py/tree/main/tests
[test_docs_dir]: ./index.md
