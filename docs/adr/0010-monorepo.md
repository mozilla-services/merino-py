# Adopt Monorepo for Merino

* Status: Accepted
* Deciders: Merino devs
* Date: 2026-05-01

## Context and Problem Statement

As Firefox Suggest and New Tab page continue to grow, new features and functionalities need to be built for Merino. In addition, there is a need in building new applications to work alongside with Merino to support the products. How can we find the optimal way to manage all those code artifacts? Shall we opt for monorepo or polyrepos?

## Decision Drivers

1. Developer experience.
2. Operational complexity.

## Considered Options

* A. Monorepo
* B. Polyrepos

## Decision Outcome

Propsed option:

* A. Monorepo

The monorepo approach allows Merino developers to manage related function units (e.g. libraries and application) in the same repo, which not only eases the cognitive burden for developers when working , but also simplifies code reuse and dependency management. Tools such as `uv` can be used to assist the monorepo management and mitigate the overhead with monorepo.

The following can be adopted for Merino developers to mitigate various downsides with monorepo:

- We can adopt a stricter "component" approach for code structuring and divisions. Workspace members (i.e. components) should have clear responsbilities and boundraries.
- Naming and structure conventions can be used to accelerate testing and maintain the developer experience.
- To mitigate the immaturity of the tooling on dependency management, we can establish dependency update guidelines for all workspace packages.

## Pros and Cons of the Options

### Monorepo

Monorepo allows us to use a single git repo to home all the code artifacts, including dependencies, packages for both common libraries and applications, and other shared resources such as linting and CI/CD settings. To facilitate that, we can reshape the existing Merino repo into a workspace and use workspace members to manage individual packages including shared libraries and independent applications. Thankfully, `uv` has built-in support for workspace management.

#### Pros

* Low cognitive load: Relevant code artifacts are co-located in the same repo.
* Easy code reuse and sharing: Shared libraries and components can be used across the repo.
* Simplified dependencies management: All repo memebers share the same dependencies. Unused dependencies are easier to be identified and removed.
* Better coding consistency: The same linting and styling rules will be enforced for all repo members.
* Simpler change control: Smaller blast radius of code changes. Breaking changes can be made in one repo within one PR.
* Simplified end-to-end testing: Related services can be run and tested within the same repo.

#### Cons

* More involved package management: Compared to a single package repo, a monorepo with multiple members will require more sophisticated tooling and settings across the board.
* Workflow performance issues: As the repo grows, performance issues could emerge in local development (e.g. excessive testing time), Git operations, CI/CD (e.g. slow build and deploys).
* Extra effort in design and maintenance. Collective discipline and careful design are required to keep the workspace members well-structured and maintainable.
* Tooling maturity. Certain features are still missing in `uv` on workspace management. For instance, it does not support [sharing dependencies across workspace members][1]. Will have to work around those with sub-optimal alternatives.

### Polyrepos

As opposed to monorepo, polyrepos use multiple repos to manage individual functional components, respectively. Each of them would has its own packages, tests, dependencies, and CI/CD settings. They can be either used as a dependent package (once published to a registry) by other projects or run as an application itself. This is Merino's current repo strcuture, for instance, the [Merino extension][2] is managed in its own repo and published to PyPI ([moz-merino-ext][3]) so that Merino can use it.

#### Pros

* Smaller codebases with clear boundary: Each repo only cares one concern.
* Autonomy: The choices of tooling, dependencies, styling, workflows are up to the repo owners.
* Smooth workflow: The build-test-deploy workflow is more straightforward and performance than that of monorepo.

#### Cons

* High cognitive load, particularly with multiple highly contextual and inter-dependent repos.
* The risk of "Dependency Hell": Each repo manages its own dependencies, extra effort is needed to avoid dependencies conflicts.
* Duplication: Code duplication and common tasks such as linting and CI/CD settings need to be written and configured for every repo.
* Harder to maintain consistency: Each repo could develop its own conventions and bespoke workflows that are harmful for maintainability and cross-functional collaboration.

## Links <!-- optional -->

* [1]: https://github.com/astral-sh/uv/issues/8949
* [2]: https://github.com/mozilla-services/moz-merino-ext
* [3]: https://pypi.org/project/mozilla-merino-ext/
