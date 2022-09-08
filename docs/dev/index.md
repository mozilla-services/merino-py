# Developer documentation for working on Merino

## tl;dr

Here are some useful commands when working on Merino.

### Run the main app

Once Poetry is installed, install all the dependencies:

```
$ poetry install
```

After that, you should be to run Merino as follows:

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

[Pre-built code docs are also available](/merino/rustdoc/).

[mdbook]: https://rust-lang.github.io/mdBook/

## Local configuration

The default configuration of Merino is `development`, which has human-oriented
logging and debugging enabled. For settings that you wish to change in the
development configuration, you have two options, listed below.

> For full details, make sure to check out the documentation for
> [Merino's setting system](../ops.md).

### Update the defaults

Dynaconf is used for all configuration management in Merino, where 
values are specified in the `merino/configs/` directory in `.toml` files.
Environment variables take precedence over the values set in the `.toml` files, so
any environment variable set will automatically override defaults. By the same token,
any config file that is pointed to will override the `merino/configs/default.toml` file.

If the change you want to make makes the system better for most development
tasks, consider adding it to `config/development.yaml`, so that other developers
can take advantage of it. You can look at `config/base.yaml`, which defines all
requires configuration, to see an example of the structure.

It is not suitable to put secrets in `config/development.yaml`.

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

## Project crates



### [`merino`](../rustdoc/merino/)

This is the main Merino application, and one of the _binary_ crates in the
repository. It brings together and configures the other crates to create a
production-like environment for Firefox Suggest.

### [`merino-settings`](../rustdoc/merino_settings/)

This defines and documents the settings of the application. These settings
should be initialized by one of the _binary_ crates, and passed into the other
crates to configure them.

### [`merino-web`](../rustdoc/merino_web/)

This crate provides an HTTP API to access Merino, including providing
observability into the running of the application via that API.

### [`merino-suggest`](../rustdoc/merino_suggest/)

This is a _domain_ crate that defines the data model and traits needed to
provide suggestions to Firefox.

### [`merino-cache`](../rustdoc/merino_cache/)

This crate contains domain models and behavior for Merino's caching
functionality.

### [`merino-adm`](../rustdoc/merino_adm/)

This crate provides integration with the AdMarketplace APIs, and implements the
traits from `merino-suggest`.

### [`merino-showroom`](./showroom.html)

This is not a Rust crate, but instead a small Javascript application. It can be
used to test Merino during development and demos.

### [`merino-integration-tests`](../rustdoc/merino_integration_tests/)

This crate is a separate test system. It works much like `merino`, in that it
brings together the other crates to produce a complete Merino environment.
However, this binary crate produces an application that exercise the service as
a whole, instead of providing a server to manual test against.

### [`merino-integration-tests-macro`](../rustdoc/merino_integration_tests_macro/)

This crate provides a procmacro used in `merino-integration-tests`. Rust
requires that procmacros be in their own crate.

## Recommended Tools

- [rust-analyzer][] - IDE-like tools for many editors. This provides easy access
  to type inference and documentation while editing Rust code, which can make
  the development process much easier.
- [cargo-watch][] - A Cargo subcommand that re-runs a task when files change.
  Very useful for things like `cargo watch -x clippy` or
  `cargo watch -x "test -- merino-adm"`.

[rust-analyzer]: https://rust-analyzer.github.io/
[cargo-watch]: https://crates.io/crates/cargo-watch

## Recommended Reading

These works have influenced the design of Merino.

- The Contextual Services
  [Skeleton Actix project](https://github.com/mozilla-services/skeleton/)
- [Zero to Production in Rust](https://www.zero2prod.com/) by Luca Palmieri
- [Error Handling Isn't All About Errors](https://www.youtube.com/watch?v=rAF8mLI0naQ),
  by Jane "[yaahc](https://twitter.com/yaahc_/)" Lusby, from RustConf 2020.
