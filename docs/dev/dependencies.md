# Development Dependencies

## Package Dependencies

This project uses `uv` for dependency management, virtual environment management and running scripts and commands.
While you can use the vanilla virtualenv to set up the dev environment, we highly recommend to check
out [uv][1].

To install `uv`, run:
```sh
$ pipx install uv
```
Or [install][2] via your preferred method.

Feel free to browse the [pyproject.toml][3] file for a listing of dependencies
and their versions.

First, lets make sure you have a virtual environment set up with the right Python version. This service uses Python 3.13.
```sh
$ uv venv
```
See [more][4] about setting up virtual envs and Python version with uv.

Once uv is installed, and a virtual environment is created with the correct Python version, install all the dependencies:
```sh
$ uv sync --all-groups
```

Add packages to project via uv
```sh
$ uv add <package_name>
```

After that you should be to run Merino as follows:

```sh
$ uv run fastapi run merino/main.py --reload
```

## Moving from the Poetry & Pyenv Set up
If you had your environment previously set up via poetry and pyenv, here are the steps to move to `uv`. This would be a nice clean up and reset.

```sh
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
connect to. In addition, a GCS (GCP Cloud Storage) emulator, `fake-gcs-server`,
is also provided to facilitate local development and testing.

To make things simple, all these service dependencies can be started with Docker
Compose, using the `docker-compose.yaml` file in the `dev/` directory.
Notably, this does not run any Merino components that have source
code in this repository.

```sh
# Run this at the Merino's project root
$ docker compose -f dev/docker-compose.yaml up

# Or run services in deamon mode
$ docker compose -f dev/docker-compose.yaml up -d

# Stop it
$ docker compose -f dev/docker-compose.yaml down

# Shortcuts are also provided
$ make docker-compose-up
$ make docker-compose-up-daemon
$ make docker-compose-down
```

### Redis

Two Redis servers (primary & replica) are listening on ports 6379 and 6380,
and can be connected via `redis://localhost:6379` and `redis://localhost:6380`,
respectively.

This Dockerized set up is optional. Feel free to run the dependent services by
any other means as well.

### GCS Emulator

The GCS emulator is listening on port 4443 and ready for both read and write
operations. Make sure you set a environment variable `STORAGE_EMULATOR_HOST=http://localhost:4443`
so that Merino's GCS clients can connect to it. For example,

```sh
$ STORAGE_EMULATOR_HOST=http://localhost:4443 make run
```

Optionally, you can create a GCS bucket and preload data into it. The preloaded
data is located in `dev/local_data/gcs_emulator/`. Say if you want to preload
a JSON file `top_picks_latest.json` into a bucket `merino-images-prodpy`, you
can create a new sub-directory `merino-images-prody` in `gcs_emulator` and then
create or copy `top_picks_latest.json` into it. Then you can set Merino's
configurations to use those artifacts in the GCS emulator.

```
# File layout of the preloaded GCS data

dev/local_data
└── gcs_emulator
    └── merino-images-prodpy  <- GCS Bucket ID
        └── top_picks_latest.json  <- A preloaded GCS blob
```

Note that `dev/local_data` will not be checked into the source control nor the
docker image of Merino.

### Dev Helpers

The docker-compose setup also includes some services that can help during
development.

- Redis Commander, http://localhost:8081 - Explore the Redis database started
  above.


[1]: https://docs.astral.sh/uv/
[2]: https://docs.astral.sh/uv/getting-started/installation/
[3]: /pyproject.toml
[4]: https://docs.astral.sh/uv/concepts/python-versions/
