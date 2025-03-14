# Development Dependencies

## Package Dependencies

This project uses `uv` for dependency management, virtual environment management and running scripts and commands.
While you can use the vanilla virtualenv to set up the dev environment, we highly recommend to check
out [uv][1].

To install `uv`, run:
```
pipx install uv
```
Or [install][2] via your preferred method.

Feel free to browse the [pyproject.toml][3] file for a listing of dependencies
and their versions.

First, lets make sure you have a virtual environment set up with the right Python version. This service uses Python 3.12.
```
uv venv
```
See [more][4] about setting up virtual envs and Python version with uv.

Once uv is installed, and a virtual environment is created with the correct Python version, install all the dependencies:
```
$ uv sync --all-groups
```

Add packages to project via uv
```
$ uv add <package_name>
```

After that you should be to run Merino as follows:

```
$ uv run fastapi run merino/main.py --reload
```

## Moving from the Poetry & Pyenv Set up
If you had your environment previously set up via poetry and pyenv, here are the steps to move to `uv`. This would be a nice clean up and reset.
```
# Remove your previous virtual environment. If you set up using pyenv, then:
rm .python-version
pyenv uninstall merino-py

# Uninstall pyenv
rm -rf $(pyenv root)
# or if you installed it via your OS package manager
brew uninstall pyenv
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


[1]: https://docs.astral.sh/uv/
[2]: https://docs.astral.sh/uv/getting-started/installation/
[3]: /pyproject.toml
[4]: https://docs.astral.sh/uv/concepts/python-versions/
