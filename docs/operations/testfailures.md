# What to do with test failures in CI?

1. Investigate the cause of the test failure
    - For functional tests (unit, integration or contract), logs can be found on
      [CircleCI][circleci]
    - For performance tests (load), insights can be found on [Grafana][merino_app_info] and in the
      Locust logs. To access the Locust logs see the [Distributed GCP Exection - CI Trigger][load_tests]
      section of the load test documentation.

2. Fix or mitigate the failure
    - If a fix can be identified in a relatively short time, then submit a fix
    - If the failure is caused by a flaky or intermittent functional test and the risk to the
      end-user experience is low, then the test can be "skipped", using the pytest`xfail`
      [decorator][pytest_xfail] during continued investigation. Example:
      ```python
      @pytest.mark.xfail(reason="Test Flake Detected (ref: DISCO-####)")
      ```
3. Re-Deploy
    - A fix or mitigation will most likely require a PR merge to the `main` branch that will
      automatically trigger the deployment process. If this is not possible, a re-deployment can be
      initiated manually by triggering the CI pipeline in [CircleCI][circleci].

[circleci]: https://app.circleci.com/pipelines/github/mozilla-services/merino-py
[merino_app_info]: https://earthangel-b40313e5.influxcloud.net/d/rQAfYKIVk/wip-merino-py-application-and-infrastructure?orgId=1&from=now-24h&to=now&var-environment=prodpy&refresh=1m
[merino_gcp_stage]: https://console.cloud.google.com/kubernetes/list/overview?project=moz-fx-merino-nonprod-ee93
[pytest_xfail]: https://docs.pytest.org/en/latest/how-to/skipping.html
[load_tests]: https://mozilla-services.github.io/merino-py/testing/load-tests.html
