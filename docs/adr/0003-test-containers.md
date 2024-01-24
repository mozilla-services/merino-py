# Streamline Test Coverage of Third-Party Integrations

* **Status:** Accepted
* **Deciders:** Nan Jiang & Katrina Anderson
* **Date:** 2024-01-24

## Context and Problem Statement

In 2024, it is anticipated that Merino will expand to be consumed by a greater set of Firefox
surfaces and to include more content providers. This will challenge the current feature test
strategy, which has shown weakness in detecting incompatibilities with third-party integrations.
Examples:

1. [Weather Incident with Redis Integration][1]
2. [Navigation Suggestions Error with GCP Integration][2]

The current test approach uses a combination of unit, integration, and contract feature tests,
where third-party integrations such as cloud services, data storage services, and external API
integrations are [test doubled][3] in the unit and integration tests and emulated with Docker
containers in contract tests. While test doubles might be easier to work with, they lack the
accuracy of working with real dependencies in terms of matching the production environment and
covering all the integration surfaces and concerns in tests.

Despite the potential to test with third-party integrations in contract tests, developers have
refrained due to their lack of familiarity with Docker and CI tooling, as well as their belief
in a poor return on investment for the time and effort required to create and maintain contract
tests for experimental features.

Given the Merino service context, which has a rapid development pace and a high risk tolerance,
is there a way to streamline the test strategy while ensuring robustness against third-party
integrations?

## Decision Drivers

**1. Usability & Skill Transferability**

Ease-of-use is the key criterion when we assess a tool for testing. The test strategy should
prefer tools that require less effort and time to acquire proficiency. It should be easy to
learn and work with. Ideally, any skills or knowledge acquired should be applicable across
current contexts or for future scenarios.

**2. Maturity & Expandability**

The test strategy and tooling should be able to handle known third-party Merino dependencies
in tests with a reasonable belief that it will cover future growth. Known third-party
dependencies include: REST APIs, Remote Settings, GCP Cloud Storage, Redis, and Elasticsearch.
Future dependencies include: relational DBMS such as PostgreSQL and other GCP cloud services
such as Pub/Sub.

**3. Cost Efficiency**

The worker hours and tooling expenditures associated with the implementation and execution of
the test strategy should ensure the profitability of Merino.

## Considered Options

* A. Yes. Expand the Scope of Integration Tests Using Dependency Docker Containers (Testcontainers)
* B. Yes. Reduce the Dependency Overhead in Tests Using Development and Stage Environments
* C. No. Fulfill the Current Test Strategy with Contract Test Coverage (Status quo)

## Decision Outcome

**Chosen option: A**

Overall, we believe that increasing the scope of integration tests to verify third-party
integrations with [Testcontainers][4] will be the most effective and sustainable way forward.
Testcontainers' "Test dependencies as code" approach best fulfills the Usability & Skill
Transferability and Maturity & Expandability decision drivers and long-term would prove to be
the most Cost Efficient option.

We expect there to be initial labour costs to integrating Testcontainers, but anticipate that
moving more verification responsibility to the integration test layer will be more accessible
for developers and will reduce bugs found between Merino and third-party integrations.

Testcontainers is a widely adopted container-based test platform that supports a wide range of
programming languages including Python and Rust, which are popular at Mozilla and there is
indication that Testcontainers would have applicability across services in PXI. Given the success
of Rapid Release and other experiments in Merino, it's a good candidate to use in Merino first as
a pilot test. Should we find any issues or unsoundness about it, we can always revert the decision
in the future.

## Pros and Cons of the Options

### A. Yes. Expand the Scope of Integration Tests Using Dependency Docker Containers (Testcontainers)

A preference for the unit and integration feature test layers in Merino has emerged over time.
These test layers are white-box, which means developers can more easily set up program environments
to test either happy paths or edge cases. In addition, tooling for debugging and measuring code
coverage is readily available in these layers.[Testcontainers][4] can be used to increase the scope
of integration tests, covering the backend layer logic and network communication with third-party
integrations, the current test strategy's point of weakness.

#### Pros

* Testcontainers works with any Docker image and has numerous pre-built modules. Almost all the
  existing dependencies (or their close emulators) of Merino can be run as Docker containers. As a
  result, we can use real dependencies in Merino's tests as opposed to test doubles
* Testcontainers allows developers to programmatically manage the lifecycle of containers in the
  test code. This simplifies its usage for developers, who will not need to run any Docker commands
  separately for testing
* Testcontainers, which has [recently been acquired by Docker][5], is fairly mature and supports
  many popular programming languages. There are also a large number of community maintained clients
  available for popular services such as PostgreSQL, Redis, Elasticsearch, etc.
* Testcontainers is lightweight and sandboxed, meaning service resources aren't shared and are
  cleaned up automatically, promoting test isolation and parallelization
* Docker-compose is also supported by Testcontainers, facilitating use of multiple dependency
  containers for more complex test cases
* Testcontainers supports Python, Rust and Javascript languages and works well with their respective
  test frameworks [PyTest][6], [Cargo-Test][7] and [Jest][8]

#### Cons

* A Docker runtime is required to run all the tests that depend on Testcontainers. Docker is
  already setup in CI, but developers may need to install a Docker runtime locally
* Integration tests cannot be run completely offline as Docker images need to be downloaded first
* Developers will need to understand more about how to configure and work with dependency
  containers. The development community has many popular services out of the box, but developers
  would still need to know and do more than what's required when using test doubles
* It could be challenging to provision test fixtures for the underlying containers. Feeding the
  fixture data into the containers could be complex
* Developers need to ensure version consistency across the development, testing, and production
  environments in the integration test layer
* For third-party API integrations, if the provider doesn't provide a Docker image for their API,
  Testcontainers alone will not help us much. It's possible to use fake API container generators,
  such as [Wiremock][9], but it comes with its own complexities
* Implementation of Testcontainers would require refactoring of integration tests, including the
  removal of mocks and fixtures

### B. Yes. Reduce the Dependency Overhead in Tests Using Development and Stage Environments

Using Merino's staging environment and third-party development resources in tests has been
considered. This would effectively cover the current test strategy's weakness with third-party
integrations without the cost and complexity involved with setting up test doubles or dependency
containers. However, this approach has a key challenge in how to share the stage environment
across all the test consumers (devs & CI) as most of the services do not support multi-tenant
usage and would require a significant amount of effort to support resource isolation.

#### Pros

* Best matches the production environment
* Doesn't need extra effort to create test doubles or dependencies for testing

#### Cons

* Tests cannot be run offline since they would require a network connection to interact with
  development and stage environments
* This option breaks the [Testing Guidelines & Best Practices][10] for Merino, which require tests
  to be isolated and repeatable. A dependency on shared network resources will almost certainly
  lead to test flake, reducing the confidence in the test suite
* Test execution speeds would be negatively impacted, due to the lack of sandboxing, which enables
  parallel test runs

### C. No. Fulfill the Current Test Strategy with Contract Test Coverage (Status quo)

The current test strategy, which relies on the contract tests to verify the interface between
Merino and third-party dependencies, has not been fully implemented as designed. The missing
coverage explains the current test strategy's weakness.
Examples:

1. [DISCO-2032: Weather Contract Tests][11]
2. [DISCO-2324: Add a merino-py contract test that interacts with a real Redis instance][12]
3. [DISCO-2055: Dynamic Wikipedia Contract Tests][13]

#### Pros

* The most cost-effective solution, at least in the short term, since the test framework and Docker
  dependencies are set up and integrated into CI
* The unit and integration feature test layers remain simple by using test doubles

#### Cons

* The black-box nature of contract tests makes it harder to set up the environmental conditions
  required to enable testing edge cases
* Adding dependency containers is complex, often requiring developers to have advanced knowledge
  of Docker and CI vendors (e.g. CircleCI)
* There is a high level of redundancy between unit, integration, and contract tests that negatively
  impacts development pace

## Open Questions

* How to test 3rd party API integrations? We have two options for consideration: Either use
  generic API mocking frameworks or keep status quo and rely on other means (e.g. observerbility)
  to capture API breakages. They both have pros and cons and warrant a separate ADR to discuss
  in detail

## Links

* [DISCO-2704 - Use Testcontainer for Merino][13]

<!-- References -->
[1]: https://docs.google.com/document/d/1hQKTro1ulxrurPBybUVHguVGgt7xCPED-ZJAOtlDqsU/edit#
[2]: https://github.com/mozilla-services/merino-py/pull/467
[3]: https://martinfowler.com/articles/mocksArentStubs.html#TheDifferenceBetweenMocksAndStubs
[4]: https://testcontainers.com/
[5]: https://www.docker.com/blog/docker-whale-comes-atomicjar-maker-of-testcontainers/
[6]: https://docs.pytest.org/en/7.4.x/
[7]: https://doc.rust-lang.org/cargo/guide/tests.html
[8]: https://jestjs.io/
[9]: https://wiremock.org/
[10]: https://github.com/mozilla-services/merino-py/blob/disco-2704/CONTRIBUTING.md#testing-guidelines--best-practices
[11]: https://mozilla-hub.atlassian.net/browse/DISCO-2032
[12]: https://mozilla-hub.atlassian.net/browse/DISCO-2324
[13]: https://mozilla-hub.atlassian.net/browse/DISCO-2055
[14]: https://mozilla-hub.atlassian.net/browse/DISCO-2704
