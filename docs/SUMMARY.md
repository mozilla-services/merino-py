# Summary

[Intro](./intro.md)

# General Documentation

- [Using the HTTP API](./api.md)
- [Configuring Firefox and Merino Environments](./firefox.md)
- [Data collection](./data.md)
- [Working on the Code](./dev/index.md)
  - [Content Moderation](./dev/content-moderation.md)
  - [Dependencies](./dev/dependencies.md)
  - [Logging and Metrics](./dev/logging-and-metrics.md)
  - [Middlewares](./dev/middlewares.md)
  - [Feature Flags](./dev/feature_flags.md)
  - [Release Process](./dev/release-process.md)
  - [Profiling](./dev/profiling.md)
  - [Testing & Test Strategy](./testing/index.md)
    - [Unit Tests](./testing/unit-tests.md)
    - [Integration Tests](./testing/integration-tests.md)
    - [Load Tests](./testing/load-tests.md)
    - [Contract Tests](./testing/contract-tests/index.md)
      - [Kinto Setup](./testing/contract-tests/kinto-setup.md)
      - [Client](./testing/contract-tests/client.md)
- [Operations](./operations/index.md)
  - [Rollback](./operations/rollback.md)
  - [Modify Navigational Suggestions Blocklist](./operations/blocklist-nav-suggestions.md)
  - [Modify Wikipedia Suggestions Blocklist](./operations/blocklist-wikipedia.md)
  - [Test Failures in CI](./operations/testfailures.md)
  - [Configs](./operations/configs.md)
  - [Elasticsearch](./operations/elasticsearch.md)
  - [Jobs](./operations/jobs.md)
    - [Navigational Suggestions](./operations/jobs/navigational_suggestions.md)


# ADR
- [Archive](./adr/index.md)
  - [Load Test Framework: Locust VS K6](./adr/0001-locust-vs-k6-merino-py-performance-test-framework.md)
  - [General API Response](./adr/0002-merino-general-response.md)
