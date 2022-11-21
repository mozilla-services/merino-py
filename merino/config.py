"""Configuration for merino-py"""
from dynaconf import Dynaconf, Validator

# Validators for Merino settings.
_validators = [
    Validator("logging.level", is_in=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]),
    Validator("logging.format", is_in=["mozlog", "pretty"]),
    Validator("metrics.host", is_type_of=str),
    Validator("metrics.port", gte=0, is_type_of=int),
    Validator("metrics.dev_logger", is_type_of=bool),
    Validator("providers.accuweather.enabled_by_default", is_type_of=bool),
    Validator("providers.adm.enabled_by_default", is_type_of=bool),
    Validator("providers.adm.cron_interval_sec", gt=0),
    Validator("providers.adm.resync_interval_sec", gt=0),
    Validator("providers.adm.score", gte=0, lte=1),
    Validator("providers.adm.backend", is_in=["remote-settings", "test"]),
    Validator("providers.adm.score_wikipedia", gte=0, lte=1),
    Validator("providers.wikifruit.enabled_by_default", is_type_of=bool),
    Validator("runtime.query_timeout_sec", is_type_of=float, gte=0),
    Validator("sentry.mode", is_in=["disabled", "release", "debug"]),
    Validator("sentry.env", is_in=["prod", "stage", "dev"]),
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
