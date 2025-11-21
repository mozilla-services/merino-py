# A Gentle Guide for the New Person

This guide presumes that you know what [Merino](intro.md), are familiar with programming in Python 3.12+, and are looking to incorporate a new service.

<a name="setup">

## Setting up a development environment

<a name="elasticsearch">

### ElasticSearch

Merino uses several data stores, including ElasticSearch. You can read how to install and run a local only instance by following [this guide](https://www.elastic.co/docs/deploy-manage/deploy/self-managed/install-elasticsearch-docker-basic).

It's important to remember that elastic search is a mapping based data storage system. This means that you need to specify the index declaration, as well as the index specification. The Declaration can be done in the code (see examples in [wikipedia](https://github.com/mozilla-services/merino-py/blob/2472bd7f1a892f06763546144b6b84f21bdb5586/merino/jobs/wikipedia_indexer/settings/v1.py#L33) and [sports](https://github.com/mozilla-services/merino-py/blob/0835b214d93a134f596b85948eadedc2a157a311/merino/providers/suggest/sports/backends/sportsdata/common/elastic.py#L27)
). The actual index creation may need to happen externally, and should be either done manually using the GCP console, or by using the internal teraform definition tooling.

Remember, when running locally, you will have admin rights to your Elasticsearch instance. This will NOT be the case in production.

**_NOTE_**: Only the AirFlow job has WRITE access to ElasticSearch. The Merino `suggest` client has only READ access. All modification or alteration operations MUST be performed by the AirFlow job.

The indexes that your jobs will have WRITE access to are defined in the elasticsearch teraform `main.tf` file (see the webservices-infra repo).
These are defined in the `elasticstack_elasticsearch_security_api_key` resources. Names can describe patterns, e.g. `enwiki-*` or `sports-*`.
You are encourged to use an index name format similar to `{platform}-{language}-{index_name}` when possible since it will make identifying the columns easier.

<a name="types">

# Types of Merino Services

Merino has two ways to provide suggestions, _off-line_ (which uses user agent locally stored data provided by Remote Settings) and _on-line_ (which provides more timely data by providing live responses to queries).

_off-line_ data sets are generally smaller, since we have limited storage capacity available. These may use the
[`csv_rs_uploader`](../merino/jobs/csv_rs_uploader) command. A good example of this is the
[`wikipedia_offline_uploader`](../merino/jobs/wikipedia_offline_uploader)
job.

_on-line_ data do not necessarily have the same size restrictions, but are instead constrained by time. These services should return a response in less than 200ms.

## Configuration

Configurations for the `jobs` and `suggest` processes are stored under `./merino/configs` and are sets of TOML files. These include:

- `ci.toml` - Continuous Integration configurations (Use only for CI tasks)
- `default.toml` - Common, core settings. These are over-ridden by the platform specific configurations.
- `development.toml`, etc. - The platform specific configurations to use. These will eventually be replaced by a single, composed `platform.toml`(name TBD).
- `default.local.toml` - A locally generated and managed configuration file. This file overrides values stored in `default.toml` and is meant for local dev and testing work, and thus may have key values and other private or specific information. (Do not check in this file. It is inlcuded in `.gitignore` for a reason ;))

Validators for the configuration options are stored in the `./merino/configs/__init__.py` file

<a name="jobs">

## Jobs

`Jobs` are various tasks that can be executed by Merino, and are located in the `./merino/jobs` directory. These jobs are invoked by calling `uv run merino-jobs {job_name}`. Running without a `{job_name}` returns a list of available jobs that can be run. For example:

```bash
> uv run merino-jobs

Usage: merino-jobs [OPTIONS] COMMAND [ARGS]...

 CLI Entrypoint

╭─ Options ─────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                            │
╰────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ wikipedia-indexer           Commands for indexing Wikipedia exports into Elasticsearch                 │
│ navigational-suggestions    Command for preparing top domain metadata for navigational suggestions     │
│ amo-rs-uploader             Command for uploading AMO add-on suggestions to remote settings            │
│ csv-rs-uploader             Command for uploading suggestions from a CSV file to remote settings       │
│ relevancy-csv-rs-uploader   Command for uploading domain data from a CSV file to remote settings       │
│ geonames-uploader           Uploads GeoNames data to remote settings                                   │
│ wiki-offline-uploader       Command for uploading wiki suggestions                                     │
│ polygon-ingestion           Commands to download ticker logos, upload to GCS, and generate manifest    │
╰────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

Please note that file paths presume you are in the Project Root directory.

A significant portion of work involves fetching and normalizing data, referred to as "ingestion". Data ingestion often requires extra time and write permissions. These are provided by the AirFlow process currently, which is managed by the Data Engineering team. Changes or work requests should use [the Data Engineering Job Intake form](https://mozilla-hub.atlassian.net/jira/software/c/projects/DENG/form/1610). Be sure to allow for high lead time for any job request.

The ingestion applications are stored under `./merino/jobs/` each provider has it's own application, since each provider is slightly different. For consistency, we use [Typer](https://typer.tiangolo.com/tutorial/) to describe the command.

Airflow uses [DAG](https://airflow.apache.org/docs/apache-airflow/stable/core-concepts/dags.html) definitions to specify job run specifications. Each DAG will invoke a specific merino job. The DAG definitions are stored under `./telemetry-airflow` which links to https://github.com/mozilla/telemetry-airflow with merino jobs defined in `merino-jobs.py`. DAGs are python command lines and look like:

```python
# Run nightly SportsData team/sport update job
# This fetches sport info, schedules, teams, etc.
with DAG(
    "merino_sports_nightly",        # Unique name of the job
    schedule_interval="0 4 * * *",  # ~ Midnight US/ET
    doc_md=DOCS,
    default_args=default_args,
    tags=tags,
) as dag:

    sport_nightly_job = merino_job(
        name="sports_nightly_update",      # Job designator
        arguments=["fetch_sports", "nightly"],      # Command line args
        secrets=[sportsdata_prod_apikey_secret],    # name of the stored secret
    )

```

Remember that you will need to create a separate PR to the [`telemetry-airflow`](https://github.com/mozilla/telemetry-airflow?tab=readme-ov-file) repo to include any changes.

Per the Data Engineering team:

> The workaround for running GKE tasks in dev DAGs is to use the [shared Airflow dev environment](https://dev.telemetry-airflow.nonprod.dataservices.mozgcp.net/home) by pushing [a telemetry-airflow Git tag](https://github.com/mozilla/telemetry-airflow/tags) that starts with dev- so it gets auto-deployed to that dev environment (as described in the [telemetry-airflow README](https://github.com/mozilla/telemetry-airflow/blob/main/README.md#deployments)).
>
> For example, Glenda Leonard was using this approach recently, pushing tags that start with dev-gleonard- followed by the commit’s short SHA, so you could do something similar. Obviously, one major downside to this approach is there can be conflicts if multiple developers are wanting to use the shared dev environment at the same time, but I believe Glenda has completed her DAG development work for the time being.

### Creating an Airflow Job

AirFlow uses Apache AirFlow. These are run under the [telemetry-airflow](https://github.com/mozilla/telemetry-airflow) repo.

- Airflow jobs DO NOT have metrics. Use logging instead.
- Airflow jobs have no local storage. Use data storage if required.
- Secrets and API keys need to be managed via Google Secret Manager (GSM). That may require filing an [DataEng SRE ticket](https://mozilla-hub.atlassian.net/jira/software/c/projects/DENG/form/1610).
- Airflow jobs are run using the Merino distribution image.

When creating an AirFlow job:

- Create the job definition in `./merino/jobs` as a python [Typer](https://typer.tiangolo.com/) Command Line Interface(CLI) job.
- Ensure that each `job` has a distinct command line.
- Create an SRE ticket requesting GSM storage of any access credentials required by the job. _NOTE_: You should specify the secret identifier for this value, since you will need to refer to it later.
- Create a sub task ticket for the generation of the Airflow Job for telemetry
- Create a new branch in `telemetry-airflow` that includes the Jira ticket identifier created prior (e.g. `git checkout -b feat/DISCO-1234_new_provider`)
- Modify the `telemetry-airflow/dags/merino_jobs.py` (Note, this is in the `telemetry-airflow` repo, not the `merino-py` repo which may include `telemetry-airflow` as a linked repository).

<a name="suggest">

## Suggest

Suggest operates by exposing a REST like interface. Each `Provider` has specific code relating to how the data should be fetched and displayed. Categories of providers can be gathered under a group to take advantage of python subclassing.

A **Provider** instantiates it's service (see `initialize()`) and optionally validates and conditions the query and handles the incoming HTTP request (see `query()`).
Providers instantiate a **Backend**, which resolves individual datum (See `query(str)`) requests and returns a list of `merino.providers.suggest.base.BaseSuggestion`. The Backend is also responsible for managing and updating the **Manifest** data block (see [Manifest](#manifest)) via the `fetch_manifest_data()` and `build_and_upload_manifest_file()` methods.

See `merino.providers.suggest.skeleton` for a general use template that modules could use.

As an example, `curl "http://localhost:8000/api/v1/suggest?q=jets+game&provider=sports"` will return a list of suggestions from the `sports` provider (which noted the team name `jets` and the extra keyword `game`)

The list of Providers is controlled by `./merino/suggest/manager.py`, in the `_create_provider()` method. This is driven by the configuration files. Note that each provider listed in the configuration file _must_ specify a `type` that matches one of the listed `ProviderType` enum. `manager.py` entries return a `Provider`, as well as create the `Backend` and any other initialization. Be aware that any fatal error or unhandled exception at this time can cause Merino to fail to load, and thus bring the system down.

Each provider is generally described by code stored under `./merino/providers/suggest/{provider_type}`. While the `Provider` should be reasonably generic, it may have one or more `Backends` which are responsible for connecting to the quick response data for this suggestion provider. This may require accessing data storage or proxying calls to an external provider. The `backend` should contain all specialized code for this.

<a name="manifest" />

### Manifest

A `Manifest` in this context is the site metadata associated with a given provider. This metadata can include things like the site icon, description, weight, and other data elements (_**TODO**_: Need to understand this data better).

Metadata is generally fetched from the site by a `job`, which may call a `Provider._fetch_manifest()` method to create and upload the data to a GCS bucket. This can be wrapped by the `merino.providers.manifest.backends.protocol.ManifestBackend.fetch()` If needed later by Merino web services, that bucket will be read and the Manifest data used to construct the `Suggestion`.

`Manifest`s contain a list of `Domain`s and a list of partner dictionaries.

`Domain`s are:

- **rank**: unique numeric ranking for this item.
- **domain**: the host domain without extension (e.g. for `example.com` the domain would be `example`)
- **categories**: a list of business categories for this domain (**TODO**: where are these defined?)
- **url**: the main site URL
- **title**: site title or brief description
- **icon**: URL to the icon stored in CDN
- **serp_categories**: list of numeric category codes (defined by `merino.providers.suggest.base.Category`)
- **similars**: [Optional] Similar words or common misspellings.

Partners are a set of dictionaries that contain values about **TODO**: ???. The dictionaries may specify values such as:

- **"domain"**: the host name of the partner (e.g. `example.com`)
- **"url"**: preferred URL to the partner
- **"original_icon_url"**: non-cached, original source URL for the icon.
- **"gcs_icon_url"**: URL to the icon stored in CDN

It's important to note that the `Manifest` is a [Pydantic BaseModel](https://docs.pydantic.dev/latest/api/base_model/), and as such, the elements are not directly accessible.

## Pre Commit checklist

Ensure that the following pass without error:

- `make format` -- applies formatting to the python files
- `make lint` -- General formatting and checks to the code.
- `make unit-tests` -- validate the code operation (note: adding `-sx` to the `Makefile` `pytest` line will cause tests to fail on first error. While this is useful for local testing, it should NOT be included in commits.)
- `make integration-tests` -- Contract tests for the API.

Merino has a Code Coverage requirement of 95% coverage (including Unit and Integration Tests).

# Merging and development

Lessons learned:

- When making changes to the `webservices-infra` repo, your changes may require `atlantis`. Run `atlantis apply` _*AFTER*_ the PR has been approved but _*BEFORE*_ the PR has been merged. You will need to make sure that your branch is up-to-date with `main`, so several syncs may be required.
