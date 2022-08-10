from dynaconf import Dynaconf, Validator

# Validators for Merino settings.
_validators = [
    Validator("logging.level", is_in=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]),
    Validator("logging.format", is_in=["json"]),
    Validator("remote_settings.record_type", is_in=["data", "offline-expansion-data"]),
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
    ],
    environments=True,
    env_switcher="MERINO_ENV",
    validators=_validators,
)
