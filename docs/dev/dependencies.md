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
$ uv sync --all-groups --all-packages
```

Add packages to project via uv

```sh
$ uv add <package_name>
```

After that you should be to run Merino as follows:

```sh
$ uv run fastapi run apps/merino/merino/main.py --reload
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

# Also start an Elasticsearch cross-cluster replication follower (see below)
$ make docker-compose-up-ccr

# Stop it and delete all volumes, including Elasticsearch data
$ make docker-compose-down-v
```

Settings shared by these services, such as the Elastic stack version, ports and
license type, are in `dev/.env`.

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
data is located in `dev/local_setup/gcs/`. Say if you want to preload
a JSON file `top_picks_latest.json` into a bucket `merino-images-prod`, you
can create a new sub-directory `merino-images-prod` in `gcs` and then
create or copy `top_picks_latest.json` into it. Then you can set Merino's
configurations to use those artifacts in the GCS emulator.

```
# File layout of the preloaded GCS data

dev/local_setup
└── gcs
    └── merino-images-prod  <- GCS Bucket ID
        └── top_picks_latest.json  <- A preloaded GCS blob
```

Note that any contents in `dev/local_setup/gcs` will not be checked into the source control nor the
docker image of Merino. (There are exceptions to this, e.g. logos necessary for tests. These
exceptions are managed in the root `.gitignore` file.)

### Elasticsearch

A single-node Elasticsearch cluster (`es01`) listens on port 9200 (`ES_PORT`), and
Kibana on port 5601 (`KIBANA_PORT`). The cluster is built from
`dev/local_setup/elasticsearch/Dockerfile`, which installs the plugins used in
production. It runs on the free basic license (`LICENSE=basic` in `dev/.env`). The one-shot `es-setup` service creates the indices and seeds a few documents
from `dev/local_setup/elasticsearch/`. See the [new person guide](../noob_guide.md#elasticsearch)
for example queries.

#### Trial license

> **Note:** Cross-cluster replication is a paid (Platinum) feature, so the multi-cluster
> setup (`make docker-compose-up-ccr`) moves **both** `es01` and `es02` onto Elastic's
> 30-day **trial** license. The default setup stays on basic.

The `es-ccr-setup` service starts the trial on each cluster through the
[start trial API](https://www.elastic.co/guide/en/elasticsearch/reference/current/start-trial.html),
unless a trial is already active. A cluster can only start a trial once, and the trial
is stored in the cluster's data volume (`esdata01`, `esdata02`). The 30 days therefore
count from the first `make docker-compose-up-ccr` on that volume. Running
`make docker-compose-up-daemon` afterwards leaves `es01` on the trial until it expires.

Once the trial expires, the cluster falls back to the basic license. Everything other
than cross-cluster replication keeps working, but the CCR follower stops replicating,
and `es-ccr-setup` fails with a message saying the trial was already used. To start a
new trial, wipe the volumes and start again:

```sh
$ make docker-compose-down-v   # deletes all local Elasticsearch data
$ make docker-compose-up-ccr
```

#### Cross-cluster replication (CCR)

In production, the Wikipedia indexer writes to a leader cluster, and other clusters
replicate its indices through CCR auto-follow. To emulate this locally, start the
services with the `ccr` Compose profile:

```sh
$ make docker-compose-up-ccr
# equivalent to
$ docker compose --env-file dev/.env -f dev/docker-compose.yaml --profile ccr up -d
```

This adds two services:

- `es02`, a second single-node cluster (`docker-cluster-follower`) that acts as the
  follower. It listens on port 9201, which you can change with `ES_FOLLOWER_PORT`.
- `es-ccr-setup`, a one-shot service that runs
  `dev/local_setup/elasticsearch/ccr_setup.sh`. The script starts the trial license on
  both clusters (see above), registers `es01` as the
  remote cluster `leader` on `es02` and creates an auto-follow pattern named
  `wikipedia`. The pattern follows leader indices that match `*wiki-*` or `*sports-*`,
  excludes `temp-*`, and gives each follower index the same name as its leader index.

Auto-follow only picks up indices created **after** the pattern exists, so the
indices seeded by `es-setup` are not replicated. Run the indexer against `es01`
(`http://localhost:9200`) to create a followed index, then inspect the follower:

```sh
$ curl "http://localhost:9201/_ccr/stats?pretty"
$ curl "http://localhost:9201/_cat/indices?v"
```

`make docker-compose-down` and `make docker-compose-down-v` also stop the `ccr`
profile services. See
[Cross-cluster replication](../operations/jobs/dynamic-wiki-indexer.md#cross-cluster-replication)
for how the indexer handles followers.

### Dev Helpers

The docker-compose setup also includes some services that can help during
development.

- Redis Commander, http://localhost:8081 - Explore the Redis database started
  above.

[1]: https://docs.astral.sh/uv/
[2]: https://docs.astral.sh/uv/getting-started/installation/
[3]: /pyproject.toml
[4]: https://docs.astral.sh/uv/concepts/python-versions/
