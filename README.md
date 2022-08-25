# merino-py

The service that powers Firefox Suggest.

## Development

### Setup

This project uses [Poetry][1] for dependency management. While you can use the
vanilla virtualenv to set up the dev environment, we highly recommend to check
out [pyenv][2] and [pyenv-virtualenv][3], as they work nicely with Poetry.
Follow the insturctions to install [pyenv][4], [pyenv-virtualenv][5], and
[poetry][6].

Once Poetry is installed, install all the dependencies:

```
$ poetry install
```

After that you should be to run Merino as follows:

```
$ poetry run uvicorn merino.main:app --reload

# Or you can fire up a poetry shell to make it shorter
$ poetry shell
$ uvicorn merino.main:app --reload
```

### Shortcuts

Following common actions are provided via Makefile for convenience:

```
# Just like `poetry install`
$ make install

# Run all linting checks
$ make lint

# Run all formatters
$ make format

# Run tests
$ make test

# Run merino-py with the auto code reloading
$ make dev

# Run merino-py without the auto code reloading
$ make run

# Run contract tests
$ make contract-test

# Run contract tests cleanup
$ make contract-test-clean

```

### Configuration

Most project configurations are managed by `pyproject.toml` through Poetry.
You can also configure other tools such as mypy and black in `pyproject.toml`
except for flake8 which is configured by `.flake8`.

### Linting

We use black, flake8, isort, mypy, and pydocstyle for linting and static type
analysis. Those are already installed when you set up the dev environment, you
can run those checks manually. There is also a git hook, enforced by [pre-commit][7],
that runs those before you commit code changes to the repo. You can install this
git hook by:

```
$ pre-commit install
$ pre-commit install-hooks
```

[1]: https://python-poetry.org/
[2]: https://github.com/pyenv/pyenv
[3]: https://github.com/pyenv/pyenv-virtualenv
[4]: https://github.com/pyenv/pyenv#installation
[5]: https://github.com/pyenv/pyenv-virtualenv#installation
[6]: https://python-poetry.org/docs/#installation
[7]: https://pre-commit.com/
