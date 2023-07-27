# Configuring Merino (Operations)

## Settings

Merino's settings are managed via Dynaconf and can be specified in two ways: by a
TOML file in the `merino/configs/` directory, or via environment variables. Environment
variables take precedence over the values set in the TOML files. TOML files set with the
same environment name that is currently activated also automatically override defaults.
Any config file that is pointed to will override the `merino/configs/default.toml` file.
Read below for more specific details.

### [File organization](#file-organization)

These are the settings sources, with later sources overriding earlier ones.

- A `config.py` file establishes a Dynaconf instance and environment-specific values
are pulled in from the corresponding TOML files and environment variables. Other
configurations are established by files that are prefixed with `config_*.py`,
such as `config_sentry.py` or `config_logging.py`.

- Per-environment configuration files are in the `configs` directory. The environment
  is selected using the environment variable `MERINO_ENV`. The settings for
  that environment are then loaded from `configs/${env}.toml`, if the file/env exists. The
  default environment is "development". A "production" environment is also
  provided.

- Local configuration files are not checked into the repository, but if created should be named
  `configs/development.local.toml`, following the format of `<environment>.local.toml`.
  This file is listed in the `.gitignore` file and is safe to use for local configuration.
  One may add secrets here if desired, though it is advised to exercise great caution.

### General

- All environments are prefixed with `MERINO_`. This is established in the
  `config.py` file by setting the `envvar_prefix="MERINO"` for the Dynaconf
  instance. The first level following `MERINO_` is accessed with a single underscore `_`
  and any subsequent levels require two underscores `__`. For example,
  the logging format can be controlled from the environment variable
  `MERINO_LOGGING__FORMAT`.

- Production environment variables are set by SRE and stored in the
  cloudops project in the `configmap.yml` file. Contact SRE if you require
  information or access on this file, or request access to the cloudops infra
  repo.

- You can set these environment variables in your setup by modifying the `.toml` files.
  Conversely, when using `make`, you can prefix `make run` with overrides to the
  desired environment variables using CLI flags.

  Example:
  `MERINO_ENV=production MERINO_LOGGING__FORMAT=pretty make dev`

- `env` (`MERINO_ENV`) - Only settable from environment variables. Controls
  which environment configuration is loaded, as described above.

- `debug` (`MERINO_DEBUG`) - Boolean that enables additional features to debug
  the application. This should not be set to true in public environments, as it
  reveals all configuration, including any configured secrets.

- `format` (`MERINO_LOGGING__FORMAT`) - Controls the format of outputted logs in
  either `pretty` or `mozlog` format. See [../config_logging.py][log].

### Caveat

Be extra careful whenever you need to reference those deeply nested settings
(e.g. `settings.foo.bar.baz`) in the hot paths of the code base, such as middlewares
or route handlers. Under the hood, Dynaconf will perform a dictionary lookup
for each level of the configuration hierarchy. While it's harmless to do those
lookups once or twice, it comes a surprisingly high overhead if accessing them
repeatedly in the hot paths. You can cache those settings somewhere to mitigate
this issue.

### Deployment

This group currently features a single setting:

- `deployment.canary` (`MERINO_DEPLOYMENT__CANARY`) - a boolean that represents
whether the pod running this application is deployed as a canary. The value is
added as a constant tag `deployment.canary` with type `int` to emitted metrics.
Note that this setting is supposed to be controlled exclusively by deployment
tooling.

### Runtime Configurations

- `runtime.query_timeout_sec` (`MERINO_RUNTIME__QUERY_TIMEOUT_SEC`) - A floating
  point (in seconds) indicating the maximum waiting period for queries issued within
  the handler of the `suggest` endpoint. All the unfinished query tasks will be
  cancelled once the timeout gets triggered. Note that this timeout can also be
  configured by specific providers. The provider timeout takes precedence over this
  value.

### API Configurations

- `default.web.api.v1.client_variant_max` (`MERINO_WEB__API__V1__CLIENT_VARIANT_MAX`)
- A non-negative integer to contol the limit of optional client variants passed
  to suggest endpoint as part of experiments or rollouts.  Additional validators
  can/will be implemented to ensure a limitation on the number of variants passed
  to the request. See: https://mozilla-services.github.io/merino/api.html#suggest.

- `default.web.api.v1.query_character_max` (`MERINO_WEB__API__V1__QUERY_CHARACTER_MAX`)
- A non-negative integer value that is passed into the `max_length` parameter
  of the FastAPI Query object constructor.  This limits the string character length
  of a given query string, in this case the total string length count for the suggestion query.

- `default.web.api.v1.client_variant_character_max` (`MERINO_WEB__API__V1__CLIENT_VARIANT_CHARACTER_MAX`)
- A non-negative integer value that is passed into the `max_length` parameter
  of the FastAPI Query object constructor.  This limits the string character length
  of a given query string, in this case the total string length count for client variants.


### Logging

Settings to control the format and amount of logs generated.

- `logging.format` (`MERINO_LOGGING__FORMAT`) - The format to emit logs in. One of

  - `pretty` (default in development) - Multiple lines per event, human-oriented
    formatting and color.
  - `mozlog` (default in production) - A single line per event, formatted as
    JSON in [MozLog](https://wiki.mozilla.org/Firefox/Services/Logging) format.

- `logging.level` (`MERINO_LOGGING__LEVEL`) - Minimum level of logs that should
  be reported. This should be a number of _entries_ separated by commas (for
  environment variables) or specified as list (TOML).

  Each entry can be one of `CRITICAL`, `ERROR`, `WARN`, `INFO`,  or `DEBUG` (in
  increasing verbosity).

### Metrics

Settings for Statsd/Datadog style metrics reporting.

- `metrics.host` (`MERINO_METRICS__HOST`) - The IP or hostname to send metrics
  to over UDP. Defaults to localhost.

- `metrics.port` (`MERINO_METRICS__PORT`) - The port to send metrics to over
  UDP. Defaults to 8092.

- `metrics.dev_logger` (`MERINO_METRICS__DEV_LOGGER`) - Whether or not to send
  metrics over to the logger. Should only be used for non-production environments.

### Sentry

Error reporting via Sentry.

- `sentry.mode` (`MERINO_SENTRY__MODE`) - The type of Sentry integration to
  enable. One of `release`, `debug`, or `disabled`. The `debug` setting
  should only be used for local development.

If `sentry.mode` is set to `release`, then the following two settings are
required:

- `sentry.dsn` (`MERINO_SENTRY__DSN`) - Configuration to connect to the Sentry project.
- `sentry.env` (`MERINO_SENTRY__ENV`) - The environment to report to Sentry.
  Probably "prod", "stage", or "dev".

If `sentry.mode` is set to `disabled`, no Sentry integration will be activated.
If it is set to `debug`, the DSN will be set to a testing value
recommended by Sentry, and extra output will be included in the logs.

### Remote_settings

Connection to Remote Settings. This is used by the Remote Settings suggestion
provider below.

- `remote_settings.server` (`MERINO_REMOTE_SETTINGS__SERVER`) - The server to
  sync from. Example: `https://firefox.settings.services.mozilla.com`.

- `remote_settings.bucket` (`MERINO_REMOTE_SETTINGS__BUCKET`) -
  The bucket to use for Remote Settings providers if not specified in the
  provider config. Example: "main".

- `remote_settings.collection`
  (`MERINO_REMOTE_SETTINGS__COLLECTION`) - The collection to use for
  Remote Settings providers if not specified in the provider config. Example:
  "quicksuggest".

### Location

Configuration for determining the location of users.

- `location.maxmind_database` (`MERINO_LOCATION__MAXMIND_DATABASE`) - Path to a
  MaxMind GeoIP database file.

### [Redis](#redis)

Global Redis settings. The weather provider optionally uses Redis to cache weather suggestions.

- `redis.server` (`MERINO_REDIS__SERVER`) - The Redis server URL, in the form of
  `redis://localhost:6379`.

### AccuWeather

Configuration for using AccuWeather as a weather backend
  - `api_key` (`MERINO_ACCUWEATHER__API_KEY`) - The API key to AccuWeather's API
    endpoint. In production, this should be set via environment variable as a secret.
  - `url_base` (`MERINO_ACCUWEATHER__URL_BASE`) - The base URL of AccuWeather's
    API endpoint.
  - `url_param_api_key` (`MERINO_ACCUWEATHER__URL_PARAM_API_KEY`) - The parameter
    of the API key for AccuWeather's API endpoint.
  - `url_current_conditions_path` (`MERINO_ACCUWEATHER__URL_CURRENT_CONDITIONS_PATH`) -
    The URL path for current conditions.
  - `url_forecasts_path` (`MERINO_ACCUWEATHER__URL_FORECASTS_PATH`) - The URL path
    for forecasts.
  - `url_postalcodes_path` (`MERINO_ACCUWEATHER__URL_POSTALCODES_PATH`) - The URL path
    for postal codes.
  - `url_postalcodes_param_query` (`MERINO_ACCUWEATHER__URL_POSTALCODES_PARAM_QUERY`) -
    The query parameter for postal codes.
  - `url_param_partner_code` (`MERINO_ACCUWEATHER__URL_PARAM_PARTNER_CODE`) -
    The query parameter for the [partner code](https://apidev.accuweather.com/developers/partner-code)
    to append to URLs in the current conditions and forecast responses.
  - `partner_code` (`MERINO_ACCUWEATHER__PARTNER_CODE`) -
    The partner code to append to URLs in the current conditions and forecast responses.

### AMO API 

- `api_url` (`MERINO_AMO__DYNAMIC__API_URL`) - the base URL of the Addons API.

### Provider Configuration

The configuration for suggestion providers.

#### Adm Provider

These are production providers that generate suggestions.

- Remote Settings - Provides suggestions from a RS collection, such as the
  suggestions provided by adM. See also the top level configuration for Remote
  Settings above.
  - `type` (`MERINO_PROVIDERS__ADM__TYPE`) - The type of this provider, should be `adm`.
  - `enabled_by_default` (`MERINO_PROVIDERS__ADM__ENABLED_BY_DEFAULT`) - Whether
    this provider is enabled by default.
  - `backend` (`MERINO_PROVIDERS__ADM__BACKEND`) - The backend of the provider.
    Either `remote-settings` or `test`.
  - `resync_interval_sec` (`MERINO_PROVIDERS__ADM__RESYNC_INTERVAL_SEC`) - The time
    between re-syncs of Remote Settings data, in seconds. Defaults to 3 hours.
  - `cron_interval_sec`
    (`MERINO_PROVIDERS__ADM__CRON_INTERVAL_SEC`) - The interval of the Remote
    Settings cron job (in seconds). Following tasks are done in this cron job:
    - Resync with Remote Settings if needed. The resync interval is configured
      separately by the provider. Note that this interval should be set smaller
      than `resync_interval_sec` of the Remote Settings leaf provider.
    - Retry if the regular resync fails.
  - `score` (`MERINO_PROVIDERS__ADM__SCORE`) - The ranking score for this provider
    as a floating point number. Defaults to 0.3.

#### AccuWeather Provider
- AccuWeather - Provides weather suggestions & forecasts.
  - `type` (`MERINO_PROVIDERS__ACCUWEATHER__TYPE`) - The type of this provider, should be
    `accuweather`.
  - `backend` (`MERINO_PROVIDERS__ACCUWEATHER__backend`) - The backend of the provider.
    Either `accuweather` or `test`.
  - `cache` (`MERINO_PROVIDERS__ACCUWEATHER__CACHE`) - The store used to cache weather reports.
    Either `redis` or `none`. If `redis`, the [global Redis settings](#redis) must be set.
    Defaults to `none`.
  - `enabled_by_default` (`MERINO_PROVIDERS__ACCUWEATHER__ENABLED_BY_DEFAULT`) - Whether
    this provider is enabled by default.
  - `score` (`MERINO_PROVIDERS__ACCUWEATHER__SCORE`) - The ranking score for this provider
    as a floating point number. Defaults to 0.3.
  - `query_timeout_sec` (`MERINO_PROVIDERS__ACCUWEATHER__QUERY_TIMEOUT_SEC`) - A floating
    point (in seconds) indicating the maximum waiting period when Merino queries
    for weather forecasts. This will override the default query timeout.
  - `cached_report_ttl_sec` (`MERINO_PROVIDERS__ACCUWEATHER__CACHED_REPORT_TTL_SEC`) - The
    number of whole seconds (as an integer) indicating the time-to-live for a cached weather
    report (current conditions and forecast) for a location. After the TTL expires, the provider
    will fetch and cache the report again on the next suggestion request for that location.

#### AMO Provider

- `type` (`MERINO_PROVIDERS__AMO__TYPE`) - The type of this provider, should be `amo`.
- `enabled_by_default` (`MERINO_PROVIDERS__AMO__ENABLED_BY_DEFAULT`) - Whether
  this provider is enabled by default. Defaults to false.
- `backend` (`MERINO_PROVIDERS__AMO__BACKEND`) - The backend of the provider.
  Either `static` or `dynamic`.
- `score` (`MERINO_PROVIDERS__AMO__SCORE`) - The ranking score for this provider
  as a floating point number. Defaults to 0.3.
- `min_chars` (`MERINO_PROVIDERS__AMO__MIN_CHARS`) - The minimum number of characters
  to process a querystring.
- `resync_interval_sec` (`MERINO_PROVIDERS__AMO__RESYNC_INTERVAL_SEC`) - The re-syncing frequency 
  for the AMO data. Defaults to daily.
- `cron_interval_sec` (`MERINO_PROVIDERS__AMO__CRON_INTERVAL_SEC`) - The frequency that the cron checks
  to see if re-syncing is required. This should be more frequent than the `resync_interval_sec` to retry 
  on errors. Defaults to every minute.

#### Top Picks Provider
- Top Picks - Provides suggestions from a static domain list of the 1000 most visited websites.
  - `enabled_by_default` (`MERINO_PROVIDERS__TOP_PICKS__ENABLED_BY_DEFAULT`) - Boolean that defines
  whether this provider is enabled by default.
  - `score` (`MERINO_PROVIDERS__TOP_PICKS__SCORE`) - The ranking score for this provider as a floating
  point number with a default set to 0.25.
  - `query_char_limit` (`MERINO_PROVIDERS__TOP_PICKS__QUERY_CHAR_LIMIT`) - The minimum character limit
  for a Top Picks suggestion to be indexed and query to be processed. Represented as an integer with a
  default set to 4.
  - `firefox_char_limit` (`MERINO_PROVIDERS__TOP_PICKS__FIREFOX_CHAR_LIMIT`) - The minimum character
  limit set for short suggestion indexing and for Firefox to process a query on Merino. Represented
  as an integer. Default is set to 2.
  - `top_picks_file_path` (`MERINO_PROVIDERS__TOP_PICKS__TOP_PICKS_FILE_PATH`) - File path to the json
  file of domains, represented as a string. Either `dev/top_picks.json` in production
  or `tests/data/top_picks.json` for testing.

#### Wikipedia Dynamic Match Provider
- Wikipedia - Provider backed by the locally indexed Wikipedia through Elasticsearch.
  - `type` (`MERINO_PROVIDERS__WIKIPEDIA__TYPE`) - The type of this provider, should be
    `wikipedia`.
  - `enabled_by_default` (`MERINO_PROVIDERS__WIKIPEDIA__ENABLED_BY_DEFAULT`) - Whether
    this provider is enabled by default.
  - `backend` (`MERINO_PROVIDERS__WIKIPEDIA__backend`) - The backend of the provider.
    Either `elasticsearch` or `test`.
  - `es_url` (`MERINO_PROVIDERS__WIKIPEDIA__ES_URL`) - The URL of the cluster that we
    want to connect to.
  - `es_api_key` (`MERINO_PROVIDERS__WIKIPEDIA__ES_API_KEY`) - The base64 key used to
    authenticate on the Elasticsearch cluster specified by `es_cloud_id`.
  - `es_index` (`MERINO_PROVIDERS__WIKIPEDIA__ES_INDEX`) - The index identifier
    of Wikipedia in Elasticsearch.
  - `es_max_suggestions` (`MERINO_PROVIDERS__WIKIPEDIA__ES_MAX_SUGGESTIONS`) - The
    maximum suggestions for each search request to Elasticsearch.
  - `es_request_timeout_ms` (`MERINO_PROVIDERS__WIKIPEDIA__ES_REQUEST_TIMEOUT_MS`) - The
    timeout in milliseconds for each search request to Elasticsearch.
  - `score` (`MERINO_PROVIDERS__WIKIPEDIA__SCORE`) - The ranking score for this provider
    as a floating point number. Defaults to 0.23.

[log]:../../merino/config_logging.py
