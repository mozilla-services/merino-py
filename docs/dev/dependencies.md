# Development Dependencies

## Package Dependencies

This project uses [Poetry][1] for dependency management. While you can use the
vanilla virtualenv to set up the dev environment, we highly recommend to check
out [pyenv][2] and [pyenv-virtualenv][3], as they work nicely with Poetry.
Follow the instructions to install [pyenv][4], [pyenv-virtualenv][5], and
[poetry][6].

Feel free to browse the [pyproject.toml][7] file for a listing of dependencies
and their versions.

Once Poetry is installed, install all the dependencies:

```
$ poetry install
```

Add packages to project via poetry
```
$ poetry add <package_name>
```

After that you should be to run Merino as follows:

```
$ poetry run uvicorn merino.main:app --reload

# Or you can fire up a poetry shell to make it shorter
$ poetry shell
$ uvicorn merino.main:app --reload
```

## Service Dependencies

Merino uses a Redis-based caching system, and so requires a Redis instance to
connect to.

To make things simple, Redis (and any future service dependencies) can be
started with Docker Compose, using the `docker-compose.yaml` file in the `dev/`
directory. Notably, this does not run any Merino components that have source
code in this repository.

```shell
$ cd dev
$ docker-compose up

# Or run services in deamon mode
$ docker-compose up -d

# Stop it
$ docker-compose down


# Shortcuts are also provided
$ make docker-compose-up
$ make docker-compose-up-daemon
$ make docker-compose-down
```

Redis is listening on port 6397 and can be connected via `redis://localhost:6397`.

This Dockerized set up is optional. Feel free to run the dependent services by
any other means as well.

### Dev Helpers

The docker-compose setup also includes some services that can help during
development.

- Redis Commander, http://localhost:8081 - Explore the Redis database started
  above.


[1]: https://python-poetry.org/
[2]: https://github.com/pyenv/pyenv
[3]: https://github.com/pyenv/pyenv-virtualenv
[4]: https://github.com/pyenv/pyenv#installation
[5]: https://github.com/pyenv/pyenv-virtualenv#installation
[6]: https://python-poetry.org/docs/#installation
[7]: /pyproject.toml
