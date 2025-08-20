# A Gentle Guide for the New Person

This guide presumes that you know what [Merino](intro.md), are familiar with programming in Python 3.12+, and are looking to incorporate a new service.

## Types of Merino Services

Merino has two ways to provide suggestions, _off-line_ (which uses user agent locally stored data provided by Remote Settings) and _on-line_ (which provides more timely data by providing live responses to queries).

_off-line_ data sets are generally smaller, since we have limited storage capacity available. These may use the [`csv_rs_uploader`](../merino/jobs/csv_rs_uploader) command. A good example of this is the []`wikipedia_offline_uploader`](../merino/jobs/wikipedia_offline_uploader) job.

_on-line_ data do not necessarily have the same size restrictions, but are instead constrained by time. These services should return a response in less than 200ms.

<a name="jobs"/>
## Merino Jobs

"Jobs" are various tasks that can be executed by Merino, and are located in the `./merino/jobs` directory. These jobs are invoked by calling `uv run merino-jobs {job_name}`. Running without a `{job_name}` returns a list of available jobs that can be run. For example:

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

### Ingestion

A significant portion of work involves fetching and normalizing data.

#### Code

The ingestion applications are stored under `./merino/jobs/` each provider has it's own application, since each provider is slightly different. For consistency, we use [Typer](https://typer.tiangolo.com/tutorial/) to describe the command,

_**TODO**_ Having weird problems defining(?)/activating(?) Options. Not sure how they're supposed to be passed along.

##### Configuration

Configurations for the ingestion processes are stored under `./merino/configs` and are sets of TOML files. These include:

- `ci.toml` - Continuous Integration configurations (Use only for CI tasks)
- `default.toml` - Common, core settings. These are over-ridden by the platform specific configurations.
- `development.toml`, etc. - The platform specific configurations to use. These will eventually be replaced by a single, composed `platform.toml`(name TBD).

Validators for the configuration options are stored in the `./merino/configs/__init__.py` file

#### Curated Recommendations

Provides the set of Curated items on the New Tab page. (Probably don't want to go there, ask for help.)

#### Governance

Provides a set of "Circuit breakers" to interrupt long running or over burdensome processes

#### Jobs

This is the set of Merino Jobs that can be either run via cron, or as singletons. See [_Merino Jobs_](#jobs) above.

#### Middleware

The set of functions called on every request/response by the Merino system.

#### Providers

This is where many of the Merino provider APIs are defined. Things often blend between Web and Jobs, so it can be confusing to sort them out.

##### Manifest

A `Manifest` in this context is the site metadata associated with a given provider. This metadata can include things like the site icon, description, weight, and other data elements (_**TODO**_: Need to understand this data better).

Metadata is generally fetched from the site by a `job`, which may call a `Provider._fetch_manifest()` method to create and upload the data to a GCS bucket. If needed later by Merino web services, that bucket will be read and the Manifest data used to construct the `Suggestion`.

##### Suggest

Each `Provider` has specific code relating to how the data should be fetched and displayed. Categories of providers can be gathered under a group to take advantage of python subclassing. Once created, the provider can be included in the Merino suggestion groups by updating `merino.providers.suggest.manager._create_provider()`.

See `merino.providers.skeleton` for a general use template that modules could use.

#### Scripts

Simple utility scripts that may be useful.

#### Tests

The bank of tests (Unit and Integration) to validate code changes. All code changes should include appropriate tests.

```

```
