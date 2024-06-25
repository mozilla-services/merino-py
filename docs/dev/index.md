# Developer documentation for working on Merino

## tl;dr

Here are some useful commands when working on Merino.

### Run the main app

This project uses [Poetry][1] for dependency management.
See [dependencies](./dependencies.md) for how to install Poetry on your machine.

Install all the dependencies:

```
$ poetry install
```

Run Merino:

```
$ poetry run uvicorn merino.main:app --reload

# Or you can use a shortcut
$ make run
```

### General commands
```shell
# List all available make commands with descriptions
$ make help

# Just like `poetry install`
$ make install

# Run linter
$ make ruff-lint

# Run format checker
$ make ruff-fmt

# Run formatter
$ make ruff-format

# Run black
$ make black

# Run bandit
$ make bandit

# Run mypy
$ make mypy

# Run all linting checks
$ make -k lint

# Run all formatters
$ make format

# Run merino-py with the auto code reloading
$ make dev

# Run merino-py without the auto code reloading
$ make run

# Run unit and integration tests and evaluate combined coverage
$ make test

# Evaluate combined unit and integration test coverage
$ make test-coverage-check

# Run unit tests
$ make unit-tests

# List fixtures in use per unit test
$ make unit-test-fixtures

# Run integration tests
$ make integration-tests

# List fixtures in use per integration test
$ make integration-test-fixtures

# Build the docker image for Merino named "app:build"
$ make docker-build

# Run contract tests on existing merino-py docker image
$ make run-contract-tests

# Run contract tests, with build step
$ make contract-tests

# Run contract tests cleanup
$ make contract-tests-clean

# Run local execution of (Locust) load tests
$ make load-tests

# Stop and remove containers and networks for load tests
$ make load-tests-clean

# Generate documents
$ make doc

# Preview the generated documents
$ make doc-preview

# Profile Merino with Scalene
$ make profile

# Run the Wikipedia CLI job
$ make wikipedia-indexer job=$JOB
```

## Documentation

You can generate documentation, both code level and book level, for Merino and
all related crates by running `./dev/make-all-docs.sh`. You'll need [mdbook][]
and [mdbook-mermaid][], which you can install via:

```sh
make doc-install-deps
```

If you haven't installed Rust and Cargo, you can reference the official Rust
[document][].

[mdbook]: https://rust-lang.github.io/mdBook/
[mdbook-mermaid]: https://github.com/badboy/mdbook-mermaid
[document]: https://doc.rust-lang.org/cargo/getting-started/installation.html

## Local configuration

The default configuration of Merino is `development`, which has human-oriented
pretty-print logging and debugging enabled. For settings that you wish to change in the
development configuration, you have two options, listed below.

> For full details, make sure to check out the documentation for
> [Merino's setting system (operations/configs.md)](../operations/configs.md).

### Update the defaults

Dynaconf is used for all configuration management in Merino, where
values are specified in the `merino/configs/` directory in `.toml` files. Environment variables
are set for each environment as well and can be set when using the cli to launch the
Merino service.
Environment variables take precedence over the values set in the `.toml` files, so
any environment variable set will automatically override defaults. By the same token,
any config file that is pointed to will override the `merino/configs/default.toml` file.

If the change you want to make makes the system better for most development
tasks, consider adding it to `merino/configs/development.toml`, so that other developers
can take advantage of it. If you do so, you likely want to add validation to those settings
which needs to be added in `merino/config.py`, where the Dynaconf instance exists along
with its validators. For examples of the various config settings, look at `configs/default.toml`
and `merino/config.py` to see an example of the structure.

It is not advisable to put secrets in `configs/secrets.toml`.

### Create a local override

Dynaconf will use the specified values and environment variables in the
`merino/configs/default.toml` file. You can change the environment you
want to use as mentioned above, but for local changes to adapt to your
machine or tastes, you can put the configuration in `merino/configs/development.local.toml`.
This file doesn't exist by default, so you will have to create it.
Then simply copy from the other config files and make the adjustments
that you require. These files should however not be checked into source
control and are configured to be ignored, so long as they follow the `*.local.toml`
format. Please follow this convention and take extra care to not check them in
and only use them locally.

See the [Dynaconf Documentation](https://www.dynaconf.com/) for more details.

[1]: https://python-poetry.org/
