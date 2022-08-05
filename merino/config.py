from dynaconf import Dynaconf

# `root_path` = The root path for Dynaconf, DO NOT CHANGE.
# `envvar_prefix` = Export envvars with `export MERINO_FOO=bar`.
# `settings_files` = Load these files in the order.
# `environments` = Enable layered environments such as `development`, `production`, `testing` etc.
# `env_switcher` = Switch environments by `export MERINO_ENV=production`. Default: `development`.

settings = Dynaconf(
    root_path="merino",
    envvar_prefix="MERINO",
    settings_files=["configs/default_settings.toml", "configs/settings.toml"],
    environments=True,
    env_switcher="MERINO_ENV",
)
