# Assure Endpoint Functionality and Load Test Suite Integrity with Default Load Tests

* **Status:** Accepted
* **Deciders:** Katrina Anderson & Nan Jiang
* **Date:** 2024-11-04

## Context and Problem Statement

Currently, load tests for the Merino service are executed on an opt-in basis, requiring contributors
to use their judgement to execute load tests as part of a deployment to production. Contributors
opt-in to load testing by including the `[load test: (abort|warn)]` substring in their commit
message. The `abort` option prevents a production deployment if the load testing fails, while the
`warn` option provides a warning via Slack and allows the deployment to continue in the event of
failure.

This strategy has several drawbacks:
* Load tests are run infrequently, making it difficult to establish performance trends or trace
  regressions to specific changes
* Relying on contributors to decide when to run load tests has proven unreliable. Developers
  occasionally introduce changes that silently break the load testing suite, particularly when
  new dependencies are added (Example: [DISCO-3026][1])
* The SRE team currently lacks the capacity to implement a weekly load test build (Example:
  [SVCSE-2236][2])
  * On a related note, due to the same capacity issues, the SRE team has indicated that a smoke
    test suite can't be integrated into the CD pipeline until Merino moves from GCP v1 to GCP v2,
    leaving a gap in coverage (Example [DISCO-2861][3])

Given these drawbacks, is there a way to provide greater consistency and more reliable feedback on
the performance of Merino's API endpoints and the health of its load test suite?

## Decision Drivers

**Resource Consumption**\
The solution should ensure API quotas with third-party providers, such as AccuWeather, are
respected.

**Load Test Break Detection**\
The solution should notify contributors when they introduce changes that break the load tests.

**Performance Trending**\
The solution should enable the establishment of consistent and reliable performance trends for
Merino-py endpoints, allowing contributors to quickly identify regressions.

**Deployment Efficiency**\
The solution should minimize delays in the deployment process while ensuring that critical issues
are flagged promptly.

## Considered Options

* A. Turn on `[load test: warn]` by default with opt-out option
* B. Turn on `[load test: abort]` by default with opt-out option
* C. Weekly manual execution of load tests
* D. Status quo: Keep current strategy

## Decision Outcome

**Chosen option: A. Turn on `[load test: warn]` by default with opt-out option**

Until a weekly load test run and smoke tests can be incorporated into the CD pipeline, the decision
is to turn on `[load test: warn]` by default and add an opt-out option, `[load test: skip]`. This
will provide much-needed insight into the performance and health of Merino’s API endpoints, while
giving contributors early feedback on the integrity of the load test suite. Additionally, this
approach will pave the way for the deprecation of Contract Tests, reducing overall test maintenance.

**Note:** The policy for documenting load test results in the [Merino Load Test spreadsheet][4] will
remain unchanged. Contributors may decide when it's necessary to do so, for example when a load test
fails.

## Pros and Cons of the Options

### A. Turn on `[load test: warn]` by default with opt-out option

This option would ensure that load tests run automatically during deployments, with failures
generating warnings but not blocking the deployment. Contributors would have the ability to opt-out
of load tests using a new option, `[load test: skip]`.

#### Pros

* Load tests would run more frequently, providing consistent feedback on Merino API endpoints and
  acting as a lightweight smoke test
* Contributors would receive early warnings if their changes break the load test suite, allowing
  issues to be traced back to specific pull requests
* The work required to implement this change is minimal and includes:
  * Modifying the smoke load test curve to minimize runtime and API resource consumption
  * Updating the CircleCI configuration
  * Updating documentation

#### Cons
* This approach would increase deployment time by approximately 10 minutes and could worsen an
  existing issue where concurrent merges to the main branch do not queue as expected, resulting in
  simultaneous deployments that may invalidate load tests
* If production deployments were to increase dramatically, there is potential to exceed
  3rd party API quotas


### B. Turn on `[load test: abort]` by default with opt-out option

This option would also ensure that load tests run automatically during deployments, but production
deployments would be blocked if the load tests fail. Contributors would have the option to opt-out
of load tests with a new option, `[load test: skip]`.

#### Pros
_Includes the Pros from Option A, plus:_

* Ensures that broken API endpoints are not deployed to users, maintaining the integrity of the
  service

#### Cons
_Includes the Cons from Option A, plus:_

* Critical features and fixes may be delayed if the load tests themselves are broken, leading to
  unnecessary deployment blockages

### C. Weekly manual execution of load tests

This option involves a member of the DISCO team manually triggering a load test on a weekly basis.
The load test could be triggered via PR or manually via a bash script.

#### Pros
* Regular load testing would allow the team to establish meaningful performance trends
* Breaks in the load test suite would be detected within a reasonable timeframe, making them easier
  to trace

#### Cons
* This approach does not address the coverage gap for API endpoint verification during deployment
* It is time-consuming for the DISCO team, and depending on the trigger technique, it may be
  error-prone
  * For example, if a DISCO team member triggers the load test via bash script and forgets to tear
    down the GCP cluster after use, unnecessary costs will be incurred

### D. Status quo: Keep current strategy

This option involves continuing with the current opt-in approach, where load tests are only run if
contributors explicitly include them in their deployment process, until the SRE team can prioritize
test strategy changes.

#### Pros
* Requires no additional work or changes to the current setup.

#### Cons
* Breakages in the load testing suite due to environmental, configuration, or dependency changes
  will continue to go undetected
* The lack of regular load tests prevents contributors from gathering sufficient data to establish
  meaningful performance trends

<!-- References -->
[1]: https://mozilla-hub.atlassian.net/browse/DISCO-3026
[2]: https://mozilla-hub.atlassian.net/browse/SVCSE-2236
[3]: https://mozilla-hub.atlassian.net/browse/DISCO-2861?focusedCommentId=910707
[4]: https://docs.google.com/spreadsheets/d/1SAO3QYIrbxDRxzmYIab-ebZXA1dF06W1lT4I1h2R3a8/edit?gid=0#gid=0
