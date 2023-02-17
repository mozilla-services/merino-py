# Locust vs k6; Merino-py Performance Test Framework

* **Status:** Proposed
* **Deciders:** Nan Jiang, Raphael Pierzina & Katrina Anderson
* **Date:** 2023-02-17

## Context and Problem Statement

Performance testing for the Rust version of Merino was conducted with the [Locust][1] 
test framework and focused on the detection of HTTP request failures. During the 
migration of Merino from Rust to Python, performance testing was conducted with [k6][2] 
and focused on the evaluation of request latency. Going forward a unified performance 
testing solution is preferred, should the test framework be Locust or k6?

## Decision Drivers 

1. The test framework supports the current load test design, a 10-minute test run with 
   an average load of 1500RPS (see [Merino Load Test Plan][3])
2. The test framework measures HTTP request failure and client-side latency metrics
3. The test framework is compatible with the Rapid Release initiative, meaning:
   * It can execute through command line
   * It can signal failures given check or threshold criteria
   * It can be integrated into a CD pipeline
   * It can report metrics to [Grafana][4]
4. The members of the DISCO and ETE teams are able to contribute to and maintain load 
   tests written with the test framework

## Considered Options

* A. Locust
* B. k6

## Decision Outcome

Chosen option:

* **A. Locust**

Both k6 and Locust are able to execute the current load test design, report required 
metrics and fulfill the Rapid Release initiative; However, Locust's Python tech stack 
ultimately makes it the better fit for the Merino-py project. In-line with the team's 
single repository direction (see [PR][5]), using Locust will:

  * Leverage existing testing, linting and formatting infrastructure
  * Promote dependency sharing and code re-use (models & backends)

## Pros and Cons of the Options

### A. Locust

[Locust][1] can be viewed as the status quo option, since it is the framework that is 
currently integrated into the Merino-py repository and is the basis for the CD load 
test integration currently underway (see [DISCO-2113][6]). 

#### Pros

* Locust has a mature distributed load generation feature and can easily support a 1500 
  RPS load
* Locust has built-in RPS, HTTP request failure and time metrics with customizable URL 
  break-down
* Locust scripting is in Python
* Locust supports direct command line usage
* Locust is used for load testing in other Mozilla projects and is recommended by the
  ETE team

#### Cons

* Locust is 100% community driven (no commercial business), which means its 
  contribution level can wane, as was the case between 2015 and 2018
* Preliminary research indicates that reporting metrics from Locust to [Grafana][4] 
  requires the creation of custom code, a plugin or a third party integration

### B. k6

For the launch of Merino-py, performance bench-marking was conducted using a [k6][2] 
load test script (see [Merino Explorations][7]). This script was reused from the Merino 
rewrite exploration effort and has proven successful in assessing if Merino-py 
performance achieves the target p95 latency threshold, effecting preventative change 
(See [PR][8]). k6's effectiveness and popularity amongst team members is an incentive 
to pause and evaluate if it is a more suitable framework going forward.

#### Pros

* k6 is an open-source commercially backed framework with a high contribution rate
* k6 is built by Grafana Labs, inferring easy integration with dashboards
* k6 has built-in RPS, HTTP request failure and time metrics with customizable URL 
  break-down
* k6 supports direct command line usage
* k6 is feature rich, including built-in functions to generate pass/fail results and 
  create custom metrics

#### Cons

* The k6 development stack is in JavaScript/TypeScript. This means:
  * Modeling and backend layer code would need to be duplicated and maintained
  * Linting, formatting and dependency infrastructure would need to be added and 
    maintained
* k6 has an immature distributed load generation feature, with [documented][9] 
  limitations
  * k6 runs more efficiently than other frameworks, so it may be possible to achieve
    1500 RPS without distribution 

## Links 

* [DISCO-2045 - Investigate K6 load testing in Merino-py CD][10]

<!-- References -->
[1]: https://locust.io/
[2]: https://k6.io/
[3]: https://docs.google.com/document/d/1v7LDXENPZg37KXeNcznEZKNZ8rQlOhNbsHprFyMXHhs/edit?usp=sharing
[4]: https://earthangel-b40313e5.influxcloud.net/?orgId=1]
[5]: https://github.com/mozilla-services/merino-py/pull/186
[6]: https://mozilla-hub.atlassian.net/browse/DISCO-2113
[7]: https://github.com/quiiver/merino-explorations
[8]: https://github.com/mozilla-services/merino-py/pull/67#issuecomment-1266031853
[9]: https://k6.io/docs/testing-guides/running-large-tests/#distributed-execution
[10]: https://mozilla-hub.atlassian.net/browse/DISCO-2045
