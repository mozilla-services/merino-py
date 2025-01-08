# Configuring Merino (Operations)
To manage configurations and view all documentation for individual config values,
please view the [default.toml][default.toml] file.

## Settings

Merino's settings are managed via [Dynaconf][dynaconf] and can be specified in two ways:
1. a [TOML file][toml] in the `merino/configs/` [directory][configs_dir].
2. via environment variables.
Environment variables take precedence over the values set in the TOML files.
Production environment variables are managed by SRE and defined in the relevant merino-py repo.
TOML files set with the same environment name that is currently activated also automatically override defaults.
Any config file that is pointed to will override the `merino/configs/default.toml` file.


## File organization

These are the settings sources, with later sources overriding earlier ones.

- A [`config.py`][config.py] file establishes a Dynaconf instance and environment-specific values
  are pulled in from the corresponding TOML files and environment variables.
  Other configurations are established by files that are prefixed with `config_*.py`,
  such as `config_sentry.py` or `config_logging.py`.

- Per-environment configuration files are in the [`configs` directory][configs_dir].
  The environment is selected using the environment variable `MERINO_ENV`.
  The settings for that environment are then loaded from `configs/${env}.toml`, if the file/env exists. The default environment is "development". A "production" environment is also provided.

- Local configuration files are not checked into the repository,
  but if created should be named `configs/development.local.toml`,
  following the format of `<environment>.local.toml`.
  This file is listed in the `.gitignore` file and is safe to use for local configuration.
  One may add secrets here if desired, though it is advised to exercise great caution.

## General

- All environments are prefixed with `MERINO_`.
  This is established in the `config.py` file by setting the `envvar_prefix="MERINO"`
  for the Dynaconf instance.
  The first level following `MERINO_` is accessed with a single underscore `_` and any subsequent levels require two underscores `__`.
  For example, the logging format can be controlled from the environment variable `MERINO_LOGGING__FORMAT`.

- Production environment variables are set by SRE and stored in the
  cloudops project in the `configmap.yml` file.
  Contact SRE if you require information or access on this file,
  or request access to the cloudops infra repo.

- You can set these environment variables in your setup by modifying the `.toml` files.
  Conversely, when using `make`, you can prefix `make run` with overrides to the
  desired environment variables using CLI flags.

  Example:
  `MERINO_ENV=production MERINO_LOGGING__FORMAT=pretty make dev`

- `env` (`MERINO_ENV`) - Only settable from environment variables.
  Controls which environment configuration is loaded, as described above.

- `debug` (`MERINO_DEBUG`) - Boolean that enables additional features to debug
  the application.
  This should not be set to true in public environments, as it reveals all configuration,
  including any configured secrets.

- `format` (`MERINO_LOGGING__FORMAT`) - Controls the format of outputted logs in
  either `pretty` or `mozlog` format. See [config_logging.py][log].

## Caveat

Be extra careful whenever you need to reference those deeply nested settings
(e.g. `settings.foo.bar.baz`) in the hot paths of the code base, such as middlewares
or route handlers. Under the hood, Dynaconf will perform a dictionary lookup
for each level of the configuration hierarchy. While it's harmless to do those
lookups once or twice, it comes a surprisingly high overhead if accessing them
repeatedly in the hot paths. You can cache those settings somewhere to mitigate
this issue.

[default.toml]: https://github.com/mozilla-services/merino-py/tree/main/merino/configs/default.toml
[dynaconf]: https://www.dynaconf.com/
[toml]: https://toml.io/en/
[config.py]: https://github.com/mozilla-services/merino-py/blob/main/merino/config.py
[configs_dir]: https://github.com/mozilla-services/merino-py/tree/main/merino/configs
[log]: https://github.com/mozilla-services/merino-py/blob/main/merino/configs/app_configs/config_logging.py
