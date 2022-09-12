# Developer documentation for working on Merino

## tl;dr

Here are some useful commands when working on Merino.

### Run the main app

Install all the dependencies:

```
$ poetry install
```

Add packages to project via poetry
```
$ poetry add <package_name>
```

Run Merino:

```
$ poetry run uvicorn merino.main:app --reload

# Or you can fire up a poetry shell to make it shorter
$ poetry shell
$ uvicorn merino.main:app --reload
```

### General commands
```shell
# Just like `poetry install`
$ make install

# Run all linting checks
$ make lint

# Run all formatters
$ make format

# Run merino-py with the auto code reloading
$ make dev

# Run merino-py without the auto code reloading
$ make run

# Run contract tests
$ make contract-tests

# Run contract tests cleanup
$ make contract-tests-clean

# Docker
$ docker-compose up
```

## Documentation

You can generate documentation, both code level and book level, for Merino and
all related crates by running `./dev/make-all-docs.sh`. You'll need [mdBook][],
which you can get with `cargo install mdbook`.

[Pre-built code docs are also available](/merino-py/book/).

[mdbook]: https://rust-lang.github.io/mdBook/

## Local configuration

The default configuration of Merino is `development`, which has human-oriented
pretty-print logging and debugging enabled. For settings that you wish to change in the
development configuration, you have two options, listed below.

> For full details, make sure to check out the documentation for
> [Merino's setting system (ops.md)](../ops.md).

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
want to use as mentioned abouve, but for local changes to adapt to your
machine or tastes, you can put the configuration in `merino/configs/development.local.toml`.
This file doesn't exist by default, so you will have to create it.
Then simply copy from the other config files and make the adjustments
that you require. These files should however not be checked into source
control and are configured to be ignored, so long as they follow the `*.local.toml`
format. Please follow this convention and take extra care to not check them in
and only use them locally.

See the [Dynaconf Documentation](https://www.dynaconf.com/) for more details.

## Repository structure

This is a brief overview of the subdirectories found in the repository.

WIP

## Recommended Tools

WIP  - Optional, but may be useful to link to some tools we use in this project.

## Recommended Reading

WIP - May be valuable to link some docs here. Somewhat redundant as these
readings are recommended ad hoc though the individual doc pages.
