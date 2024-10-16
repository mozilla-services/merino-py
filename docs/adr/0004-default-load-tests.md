# Assure Endpoint Functionality and Load Test Suite Integrity with Default Load Tests

* **Status:** In progress
* **Deciders:** Katrina Anderson _(& Nan Jiang)?_
* **Date:** 2024-10-16

## Context and Problem Statement

Currently, load tests for the Merino service are executed on an opt-in basis, requiring contributors
to use their judgement to execute load tests as part of a deployment to production. Contributors
opt-in to load testing by including the `[load test: (abort|warn)]` substring in their commit
message. The `abort` option prevents a production deployment if the load testing fails, while the
`warn` option provides a warning via Slack and allows the deployment to continue in the event of
failure.

This strategy has several drawbacks:
* Load tests are executed infrequently, making it difficult to establish performance trends or trace
  regressions to specific changes.
* The assertion that contributors will have enough context to decide when load tests should run has
  proven unreliable. Developers occasionally introduce changes that silently break the load testing
  suite, particularly when new dependencies are added (Example [DISCO-3026][1])
* The SRE team lacks the resources to implement a weekly load test build or integrate a smoke test
  suite into the current CD pipeline, leaving gaps in coverage. (Example: [SCVC-2236][2] &
  [DISCO-2861][3])

Given these drawbacks, is there a way to provide greater consistency and more reliable feedback on
the performance of Merino's API endpoints and the health of its load test suite.

## Decision Drivers

**Load Test Break Detection**\
The solution should provide a mechanism for contributors to be notified when they have broken the
load tests.

**Performance Trending**\
The solution should enable the establishment of consistent and reliable performance trends for
Merino-py endpoints, allowing contributors to identify regressions quickly.

**Deployment Efficiency**\
The solution should minimize delays in the deployment process while ensuring that critical issues
are flagged in a timely manner.

## Considered Options

* A. Turn on `[load test: warn]` by default
* B. Turn on `[load test: abort]` by default
* C. Status quo: Keep current strategy

## Decision Outcome

**Chosen option: A. Turn on `[load test: warn]` by default**

Until the SRE team can prioritize implementing a weekly load test run and incorporating smoke tests
into the CD pipeline, the decision is to turn on `[load test: warn]` by default. This will provide
much-needed insight into the performance and health of Merino’s API endpoints while giving
contributors early feedback on the integrity of the load test suite. Additionally, this approach
will pave the way for the deprecation of Contract Tests, reducing overall test maintenance.

## Pros and Cons of the Options

### A. Turn on `[load test: warn]` by default

This option would ensure that load tests run automatically during deployments, with failures
generating warnings but not blocking the deployment.

#### Pros

* Load tests would run more frequently, providing consistent feedback on Merino API endpoints and
  functioning as a lightweight smoke test.
* Contributors would receive early warnings if their changes break the load test suite, allowing
  issues to be traced to specific pull requests.
* The work required to implement this change is minimal, consisting of updating the CircleCI
  configuration and documentation.

#### Cons
* This approach would increase deployment time by approximately 10 minutes.

### B. Turn on `[load test: abort]` by default

This option would also ensure that load tests run automatically during deployments, but production
deployments would be blocked if the load tests fail.

#### Pros
_Includes the Pros from Option A, as well as:_

* Ensures that broken API endpoints are not deployed to users, maintaining the integrity of the
  service

#### Cons
_Includes the Cons from Option A, as well as:_

* Critical features and fixes might be delayed if the load tests themselves are broken, leading to
  unnecessary blockages

### C. Status quo: Keep current strategy

This option involves continuing with the current opt-in approach, where load tests only run if
developers explicitly include them in their deployment process, until SRE can prioritize test
strategy changes in CD.

#### Pros
* Requires no additional work or changes to the current setup.

#### Cons
* Breakages in the load testing suite due to environmental, configuration, or dependency changes
  will continue to go undetected.
* The lack of regular load tests prevents contributors from collecting sufficient data to establish
  meaningful performance trends

<!-- References -->
[1]: https://mozilla-hub.atlassian.net/browse/DISCO-3026
[2]: https://mozilla-hub.atlassian.net/browse/SVCSE-2236
[3]: https://mozilla-hub.atlassian.net/browse/DISCO-2861?focusedCommentId=910707
