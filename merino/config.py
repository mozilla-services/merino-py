"""Configuration for merino-py"""
from dynaconf import Dynaconf, Validator

# Validators for Merino settings.
_validators = [
    Validator("deployment.canary", is_type_of=bool),
    Validator("logging.format", is_in=["mozlog", "pretty"]),
    Validator("logging.level", is_in=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]),
    Validator("logging.can_propagate", is_type_of=bool),
    Validator("metrics.dev_logger", is_type_of=bool),
    Validator("metrics.host", is_type_of=str),
    Validator("metrics.port", gte=0, is_type_of=int),
    Validator(
        "accuweather.url_location_key_placeholder", is_type_of=str, must_exist=True
    ),
    Validator(
        "accuweather.url_param_partner_code",
        is_type_of=str,
        must_exist=True,
        when=Validator("accuweather.partner_code", must_exist=True),
    ),
    Validator("accuweather.partner_code", is_type_of=str),
    Validator("amo.dynamic.api_url", is_type_of=str),
    Validator("providers.accuweather.enabled_by_default", is_type_of=bool),
    # The Redis server URL is required when at least one provider wants to use Redis for caching.
    Validator(
        "redis.server",
        is_type_of=str,
        must_exist=True,
        when=Validator("providers.accuweather.cache", must_exist=True, eq="redis"),
    ),
    # Set the upper bound of query timeout to 5 seconds as we don't want Merino
    # to wait for responses from Accuweather indefinitely.
    Validator(
        "providers.accuweather.query_timeout_sec", is_type_of=float, gte=0, lte=5.0
    ),
    Validator("providers.accuweather.type", is_type_of=str, must_exist=True),
    Validator("providers.accuweather.cache", is_in=["redis", "none"]),
    Validator(
        "providers.accuweather.cache_ttls.current_condition_ttl_sec",
        is_type_of=int,
        gte=0,
    ),
    Validator(
        "providers.accuweather.cache_ttls.forecast_ttl_sec", is_type_of=int, gte=0
    ),
    Validator(
        "providers.accuweather.cached_ttls.location_key_ttl_sec", is_type_of=int, gte=0
    ),
    Validator("providers.adm.backend", is_in=["remote-settings", "test"]),
    Validator("providers.adm.cron_interval_sec", gt=0),
    Validator("providers.adm.enabled_by_default", is_type_of=bool),
    Validator("providers.adm.resync_interval_sec", gt=0),
    Validator("providers.adm.score", gte=0, lte=1),
    Validator("providers.adm.type", is_type_of=str, must_exist=True),
    Validator("providers.amo.backend", is_in=["dynamic", "static"]),
    Validator("providers.amo.score", gte=0, lte=1),
    Validator("providers.amo.type", is_type_of=str, must_exist=True),
    Validator("providers.amo.min_chars", is_type_of=int, gte=1, lte=10),
    Validator("providers.top_picks.enabled_by_default", is_type_of=bool),
    Validator("providers.top_picks.score", is_type_of=float, gte=0, lte=1),
    Validator("providers.top_picks.query_char_limit", is_type_of=int, gte=1),
    Validator("providers.top_picks.firefox_char_limit", is_type_of=int, gte=1),
    Validator(
        "providers.top_picks.top_picks_file_path",
        is_type_of=str,
        is_in=[
            "dev/top_picks.json",
            "tests/data/top_picks.json",
            "dev/top_picks_for_ci.json",
        ],
    ),
    Validator("providers.wikipedia.backend", is_in=["elasticsearch", "test"]),
    Validator("providers.wikipedia.enabled_by_default", is_type_of=bool),
    Validator("providers.wikipedia.es_url", is_type_of=str),
    Validator("providers.wikipedia.es_api_key", is_type_of=str),
    Validator("providers.wikipedia.es_index", is_type_of=str),
    Validator("providers.wikipedia.es_max_suggestions", is_type_of=int, gte=1),
    Validator("providers.wikipedia.es_password", is_type_of=str),
    Validator("providers.wikipedia.es_request_timeout_ms", is_type_of=int, gte=1),
    Validator("providers.wikipedia.es_user", is_type_of=str),
    Validator("providers.wikipedia.score", gte=0, lte=1),
    Validator("providers.wikipedia.type", is_type_of=str, must_exist=True),
    # Since Firefox will time out the request to Merino if it takes longer than 200ms,
    # the default query timeout of Merino should not be greater than that 200ms.
    Validator(
        "runtime.query_timeout_sec",
        is_type_of=float,
        gte=0,
        lte=0.2,
        env=["production", "ci"],
    ),
    Validator("web.api.v1.client_variant_max", is_type_of=int, gte=0, lte=50),
    # Max set that is passed into FastAPI Query constuctor param 'max_length'.
    Validator("web.api.v1.query_character_max", is_type_of=int, gt=5, lte=500),
    Validator("web.api.v1.client_variant_character_max", is_type_of=int, gt=0, lte=100),
    # Allow a longer timeout for testing & development
    Validator(
        "runtime.query_timeout_sec",
        is_type_of=float,
        gte=0,
        lte=1.0,
        env=["testing", "development"],
    ),
    Validator("sentry.env", is_in=["prod", "stage", "dev"]),
    Validator("sentry.mode", is_in=["disabled", "release", "debug"]),
    Validator("sentry.traces_sample_rate", gte=0, lte=1),
]

# `root_path` = The root path for Dynaconf, DO NOT CHANGE.
# `envvar_prefix` = Export envvars with `export MERINO_FOO=bar`.
# `settings_files` = Load these files in the order.
# `environments` = Enable layered environments such as `development`, `production`, `testing` etc.
# `env_switcher` = Switch environments by `export MERINO_ENV=production`. Default: `development`.
# `validators` = Define validators for Merino settings.

settings = Dynaconf(
    root_path="merino",
    envvar_prefix="MERINO",
    settings_files=[
        "configs/default.toml",
        "configs/development.toml",
        "configs/production.toml",
        "configs/ci.toml",
        "configs/testing.toml",
    ],
    environments=True,
    env_switcher="MERINO_ENV",
    validators=_validators,
)
