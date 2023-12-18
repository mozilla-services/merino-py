# [short title of solved problem and solution]

* **Status:** Draft
* **Deciders:** Nan Jiang & Katrina Anderson
* **Date:** 2023-12-14

## Context and Problem Statement

In 2024, it is anticipated that Merino will expand to be consumed by a greater set of
Firefox surfaces and to include more content providers. This will challenge the current
feature test strategy, which has recently shown weakness at detecting incompatibility
with third-party integrations.

The current test approach uses a combination of unit, integration, and contract feature
tests, where third-party integrations such as cloud services, data storage services,
and external API integrations are test doubled in the lower level unit and integration tests.
While test doubles (find more details about [Test Doubles] here) might be easier to work with,
they still cannot compete with the real dependencies in terms of matching the production
environment and covering all the integration surfaces and concerns in tests.

Despite the potential to test with third-party integrations in
contract tests, developers have refrained due to the lack of familiarity with Docker and
CI tooling, as well as a perceived inadequate return on investment for the time and
effort required to create and maintain contract tests for experimental features.

Given the Merino service context, which has a rapid development pace and a high risk
tolerance, is there a way to streamline the test strategy while ensuring robustness
against third-party integrations?

## Decision Drivers

1. **Usability & Skill Transferability**

    The test strategy should prefer tools that require less effort and time to acquire
    proficiency. It should be easy to learn and work with. Ideally, any skills or knowledge
    acquired should be applicable across current contexts or for future scenarios.

1. **Maturity & Expandability**

    The test strategy and tooling should be able to handle known third-party Merino
    dependencies in tests with a reasonable belief that it will cover future growth.
    Known third-party dependencies include: REST APIs, Remote Settings, GCP Cloud Storage,
    Redis, and Elasticsearch. Future dependencies include: rational DBMS such as PostgreSQL
    and other GCP cloud services such as Pub/Sub.

1. **Cost Efficiency**

    The worker hours and tooling expenditures associated to the implementation and
    execution of the test strategy should ensure the profitability of the Merino
    service.

## Considered Options

* A. Yes. Expand the Scope of Integration Tests using dependency Docker containers
  through [Testcontainers]
* B. Yes. Expand the Scope of Integration Tests using Merino staging environment
* C. No. Fulfill the Current Test Strategy with Contract Test Coverage (Status quo)

## Decision Outcome

Chosen option: A

Testcontainers is a widely adopted container-based test platform that supports a wide
range of programming languages including those popular ones used by Mozilla.
It allows us to run any Docker containers in our tests (unit & integration) in a lightweight
and sandboxed fashion. Overall, we believe that Testcontainers' "Test dependencies as code"
approach meets all the above decision drivers well with manageable shortcomings as follows.

### Positive Consequences of Option A

* Testcontainers works with any Docker images. Almost all the existing dependencies
  (or their close emulators) of Merino can be run as Docker containers. As a result,
  we can use real dependencies in Merino's tests without solely relying on test doubles
* Testcontainers allows us to programmatically launch and manage those containers
  in tests, which drastically simplifies its usage as developers do not need to
  run any Docker commands separately for testing
* Testcontainers, which is now part of Docker, is fairly mature and supports many
  popular programming languages. There are also a large number of community maintained
  clients available for popular services such as PostgreSQL, Redis, Elasticsearch, etc.
* It's lightweight and sandboxed, meaning that we can run tests isolately in parallel
  without having to worry about sharing the same service and resource cleanup
* Docker-compose is also supported, which means we could even use Testcontainers to run
  multiple dependency containers for more complex test cases
* It works well along with existing test frameworks such as PyTest and Cargo-Test

### Negative Consequences of Option A

* It requires a Docker runtime to run all the tests that depend on Testcontainers.
  While it should not be a problem in CI, now you will need to install a Docker
  runtime locally as well
* Tests cannot be run completely offline as Docker images need to be downloaded first
* Developers need to understand more about how to configure and work with the
  dependency containers. Despite that the communite has offered many popular
  services out of the box, developers would still need to know & do more than
  what's required when using test doubles
* It could be challenging to provision test fixtures for the underlying containers
  as that'd involve certain ceremony to feed the fixture data into the containers

## Pros and Cons of Other Options <!-- optional -->

### Option B

There has been considerations of using Merino's staging services for testing in the past.
The key challenges of such approach lie in how to share the stage environment across
all the test consumsers (devs & CI) as most of the services do not support multi-tenant
usage and require significant amount of effort to support resource isolation.

#### Pros

* Best match the production environment
* Do not need extra effort to create test doubles or dependencies for testing

#### Cons

* Tests can no longer be run locally but require the services in staging as well as
  network connection
* Due to the lack of sandboxing, it's very hard to support parallel test runs because
  they all share the same test resources

### Option C

Option C maintains the status quo - continue to use test doubles in unit & integration tests.
Only use contract tests to cover key integration surfaces with real dependencies.

#### Pros

* Minimal interruption to the existing test strategy and tooling
* Enjoy the relatively low learning curve and ease-of-use of test doubles

#### Cons

* Unable to cover all integration surfaces and concerns
* Having to write and maintain many test doubles and fake services can be a chore
* High overhead to test everything at the contract test level

## Links <!-- optional -->

* [Link type] [Link to ADR] <!-- example: Refined by [ADR-0005](0005-example.md) -->
* … <!-- numbers of links can vary -->

[Test Doubles]: https://martinfowler.com/articles/mocksArentStubs.html#TheDifferenceBetweenMocksAndStubs
[Testcontainers]: https://testcontainers.com/
