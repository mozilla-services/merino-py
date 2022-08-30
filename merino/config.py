"""Configuration for merino-py"""
from dynaconf import Dynaconf, Validator

# Validators for Merino settings.
_validators = [
    Validator("logging.level", is_in=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]),
    Validator("logging.format", is_in=["mozlog", "pretty"]),
    Validator("metrics.port", gte=0),
    Validator("providers.adm.cron_interval_sec", gt=0),
    Validator("providers.adm.resync_interval_sec", gt=0),
    Validator("providers.adm.score", gte=0, lte=1),
    Validator("providers.wikifruit.enabled", is_type_of=bool),
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
        "configs/testing.toml",
        "configs/development.toml",
        "configs/production.toml",
        "configs/ci.toml",
    ],
    environments=True,
    env_switcher="MERINO_ENV",
    validators=_validators,
)
