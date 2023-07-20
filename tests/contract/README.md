# Merino Contract Tests

This directory contains source code for automated contract tests for Merino.

## Overview

The contract test suite is designed to be set up as a docker-compose CI workflow.
To simulate common use cases, the suite utilizes 6 docker containers: `client`,
`merino`, `kinto-setup`, `kinto`, `kinto-attachments`, and `redis`.

The following sequence diagram depicts container interactions during the
`remote_settings__coffee` test scenario.

**Test Scenario: remote_settings__coffee**
![Sequence diagram of the integration tests][sequence_diagram]
**Notes:**
* The interactions between `kinto` and `kinto-attachments` are not depicted.
* The diagram was composed using [Miro][sequence_diagram_miro]

### client

The `client` container consists of a Python-based test framework that executes the
contract tests. The HTTP client used in the framework can be instructed to prepare
Remote Settings data through requests to kinto and can verify Merino functionality
through requests to the Merino service.

For more details see the client [README][client_readme]

### merino

The `merino` container encapsulates the Merino service under test.

For more details, see the Merino [README][merino_readme] or project
[documentation][merino_docs].

### kinto-setup

The `kinto-setup` container consists of a Python-based program responsible for
defining the Remote Settings bucket, "main", and collection, "quicksuggest", prior
to the `merino` container startup, a pre-requisite.

For more details see the kinto-setup [README][kinto_setup_readme]

### kinto & kinto-attachments

The `kinto` container holds a minimalist storage service with synchronisation and
sharing abilities. It uses the `kinto-attachments` container to store data locally.

For more details see the Remote Settings [documentation][kinto_docs]

## Local Execution

Local execution can be expedited by simply running `make contract-tests`, from the 
repository root. This creates the Docker containers with kinto, Merino and the test 
client and runs the test scenarios against them.

```shell
make contract-tests
```

To remove contract test containers and network artifacts, execute the following from
the repository root:

```shell
make contract-tests-clean
```
Failing to run this clean command between code changes may result in your changes not 
being reflected.

See [Makefile][makefile] for details.

## Maintenance

The contract test maintenance schedule cadence is once a quarter and should include
updating the following:

1. [poetry][poetry] version and python dependencies
    * [ ] [pyproject.toml][pyproject_toml]
    * [ ] [poetry.lock][poetry_lock]
2. [Docker][docker] artifacts
    * [ ] client [Dockerfile][docker_client]
    * [ ] kinto-setup [Dockerfile][docker_kinto]
    * [ ] [docker-compose.yml][docker_compose_yml]
3. [CircleCI][circle_ci] contract test jobs
    * [ ] [config.yml][circle_config_yml]
4. Documentation
    * [ ] client [README][client_readme]
    * [ ] kinto-setup [README][kinto_setup_readme]
    * [ ] contract [README][contract_readme]

[circle_ci]: https://circleci.com/docs/
[circle_config_yml]: /.circleci/config.yml
[client_readme]: ./client/README.md
[contract_readme]: ./README.md
[docker]: https://docs.docker.com/
[docker_compose_yml]: ./docker-compose.yml
[docker_client]: ./client/Dockerfile
[docker_kinto]: ./kinto-setup/Dockerfile
[kinto_docs]: https://remote-settings.readthedocs.io/en/latest/
[kinto_setup_readme]: ./kinto-setup/README.md
[makefile]: /Makefile
[merino_docs]: /docs/SUMMARY.md
[merino_readme]: /README.md
[poetry]: https://python-poetry.org/docs/
[poetry_lock]: ./poetry.lock
[pyproject_toml]: ./pyproject.toml
[sequence_diagram]: sequence_diagram.jpg
[sequence_diagram_miro]: https://miro.com/app/board/uXjVOje8DN4=/
