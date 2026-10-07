# Developer documentation for working on Merino

## tl;dr

Here are some useful commands when working on Merino.

### Run the main app

This project uses [uv][1] for dependency management.
See [dependencies](./dependencies.md) for how to install uv on your machine.

Install all the dependencies:

```
uv sync --all-groups --all-packages
```

Run Merino:

```
$ uv run fastapi run apps/merino/merino/main.py --reload

# Or you can use a shortcut
$ make run
# To run in hot reload mode
$ make dev
```

### Checks, tests, and builds

These run through [Moon](./monorepo.md), which runs each task per project. Add
`--affected --base origin/main` to limit a run to projects changed on your branch.

```shell
# Run all linting, format, security, and type checks
$ moon run ':#quality'

# Run a single check for every project: lint, format-check, security, or typecheck
$ moon run :typecheck

# Run unit tests for every project, or for one project
$ moon run :test
$ moon run merino:test

# Forward arguments to pytest
$ moon run merino:test -- -k weather

# Run Merino integration tests (builds the Elasticsearch test image; needs Docker)
$ moon run merino:integration-test

# Run all unit tests plus integration tests and enforce the coverage gates
$ moon run :test merino:diff-coverage

# Build Docker images: merino (app:build), fleece (app-fleece:build), load-tests (merino-locust:build)
$ moon run merino:docker-build
```

### Local development helpers

```shell
# List all available make commands with descriptions
$ make help

$ make install

# Run all formatters
$ make format

# Run merino-py with the auto code reloading
$ make dev

# Run merino-py without the auto code reloading
$ make run

# List fixtures in use per unit test
$ make unit-test-fixtures

# List fixtures in use per integration test
$ make integration-test-fixtures

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
values are specified in the `apps/merino/merino/configs/` directory in `.toml` files. Environment variables
are set for each environment as well and can be set when using the cli to launch the
Merino service.
Environment variables take precedence over the values set in the `.toml` files, so
any environment variable set will automatically override defaults. By the same token,
any config file that is pointed to will override the `apps/merino/merino/configs/default.toml` file.

If the change you want to make makes the system better for most development
tasks, consider adding it to `apps/merino/merino/configs/development.toml`, so that other developers
can take advantage of it. If you do so, you likely want to add validation to those settings
which needs to be added in `apps/merino/merino/configs/__init__.py`, where the Dynaconf instance exists along
with its validators. For examples of the various config settings, look at
`apps/merino/merino/configs/default.toml`
and `apps/merino/merino/configs/__init__.py` to see an example of the structure.

It is not advisable to put secrets in `apps/merino/merino/configs/secrets.toml`.

### Create a local override

Dynaconf will use the specified values and environment variables in the
`apps/merino/merino/configs/default.toml` file. You can change the environment you
want to use as mentioned above, but for local changes to adapt to your
machine or tastes, you can put the configuration in `apps/merino/merino/configs/development.local.toml`.
This file doesn't exist by default, so you will have to create it.
Then simply copy from the other config files and make the adjustments
that you require. These files should however not be checked into source
control and are configured to be ignored, so long as they follow the `*.local.toml`
format. Please follow this convention and take extra care to not check them in
and only use them locally.

See the [Dynaconf Documentation](https://www.dynaconf.com/) for more details.

[1]: https://docs.astral.sh/uv/
