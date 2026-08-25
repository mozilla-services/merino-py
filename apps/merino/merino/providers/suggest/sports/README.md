# Running Sports Provider in Stand-Alone mode.

## Prerequisites

### Elastic Start Local

Elastic [provides](https://github.com/elastic/start-local) a stripped down, locally running version of ElasticSearch and Kibana. See that site for details, but during installation, you will need to collect the following information:

- local URL to elastic search (e.g. `http://localhost:9200`)
- API Key (this may be included in the `elastic-start-local/.env` file)

## Configurations

### Elastic Search

```toml
[development.providers.sports.es]
# If using a local instance of elastic search, otherwise point to the managed elastic instance.
dsn = "http://localhost:9200"
api_key = "ABC123...=="
request_timeout_ms = 300

```

### SportsData API

The SportsData.io API requires an API key. In addition, to reduce the number of active calls
to the SportsData.io provider, local disk caching may be used. URL results will be cached to
`.json` files in the `cache_dir` directory

```toml
[development.providers.sports.sportsdata]
api_key = "abc123..."
# cache API responses to the following directory (if blank, do not cache)
cache_dir = "./tmp/"

```

### Sports config values

The Sports provider has a number of configuration options:

```toml
[development.providers.sports]
# List of active sports to process.
# (e.g. "NBA,NHL,EPL,UCL,etc")
# See `jobs.sportsdata_jobs.common` for list of supported sports
sports = "NBA,NFL,NHL"
# `{lang}` will be inline replaced with the supported languages. Currently only `en`
event_index = "sports-{lang}-event"
team_index = "sports-{lang}-team"
max_suggestions = 5
```
