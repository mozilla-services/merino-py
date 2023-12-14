# [short title of solved problem and solution]

* **Status:** Draft
* **Deciders:** Nan Jiang & Katrina Anderson
* **Date:** 2023-12-14

## Context and Problem Statement

In 2024, it is anticipated that Merino will expand to be consumed by a greater set of
Firefox surfaces and to include more content providers. This will challenge the current
feature test strategy, which has recently shown weakness at detecting incompatibility
with third-party integrations.

The current test approach uses a combination of unit, integration and contract feature
tests, where third-party integrations are test doubled in the lower level unit and
integration tests. Despite the potential to test with third-party integrations in
contract tests, developers have refrained due to the lack of familiarity with Docker and
CI tooling, as well as a perceived inadequate return on investment for the time and
effort required to create and maintain contract tests for experimental features.

Given the Merino service context, which has a fast development pace and a high risk
tolerance, is there a way to streamline the test strategy while ensuring robustness
against third-party integrations?

## Decision Drivers

1. **Test Coverage & Scalability**

    The test strategy should be able to handle known third-party Merino dependencies in
    tests with a reasonable belief that it will cover future growth. Known third-party
    dependencies include: REST APIs, Remote Settings, GCP Data Stores & Redis.

1. **Tooling Learning Curve & Skill Transferability**

    The test strategy should prefer tools that require less effort and time to acquire
    proficiency. Ideally, any skills or knowledge acquired should be applicable across
    current contexts or for future scenarios.

1. **Cost Efficiency**

    The worker hours and tooling expenditures associated to the implementation and
    execution of the test strategy should ensure the profitability of the Merino
    service.

## Considered Options

* A. Yes. Expand the Scope of Integration Tests with Testcontainers
* B. No. Fulfill the Current Test Strategy with Contract Test Coverage (Status quo)

## Decision Outcome

Chosen option:

* A. "[option A]"

[justification. e.g., only option, which meets primary decision driver | which resolves a force or facing concern | … | comes out best (see below)].

### Positive Consequences <!-- optional -->

* [e.g., improvement of quality attribute satisfaction, follow-up decisions required, …]
* …

### Negative Consequences <!-- optional -->

* [e.g., compromising quality attribute, follow-up decisions required, …]
* …

## Pros and Cons of the Options <!-- optional -->

### Option A

[example | description | pointer to more information | …] <!-- optional -->

#### Pros

* [argument for]
* [argument for]
* … <!-- numbers of pros can vary -->

#### Cons

* [argument against]
* … <!-- numbers of cons can vary -->

### Option B

[example | description | pointer to more information | …] <!-- optional -->

#### Pros

* [argument for]
* [argument for]
* … <!-- numbers of pros can vary -->

#### Cons

* [argument against]
* … <!-- numbers of cons can vary -->
* for contile, we wrote a mock AMP endpoint, but i feel like that's too much work for both test and service engineers

## Links <!-- optional -->

* [Link type] [Link to ADR] <!-- example: Refined by [ADR-0005](0005-example.md) -->
* … <!-- numbers of links can vary -->
