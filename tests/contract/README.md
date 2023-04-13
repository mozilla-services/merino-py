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
Remote Settings data through requests to kinto and can verify merino functionality
through requests to the merino service.

For more details see the client [README][client_readme]

### merino

The `merino` container encapsulates the merino service under test.

For more details, see the merino [README][merino_readme] or project
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
repository root. This creates the Docker containers with kinto, merino and the test 
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

[client_readme]: ./client/README.md
[kinto_docs]: https://remote-settings.readthedocs.io/en/latest/
[kinto_setup_readme]: ./kinto-setup/README.md
[merino_docs]: ../../docs/SUMMARY.md
[merino_readme]: ../../README.md
[sequence_diagram]: sequence_diagram.jpg
[sequence_diagram_miro]: https://miro.com/app/board/uXjVOje8DN4=/
[makefile]: ../../../Makefile
