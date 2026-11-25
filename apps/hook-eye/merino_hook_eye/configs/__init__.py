"""Configuration for merino-hook-eye."""

from pathlib import Path

from dynaconf import Dynaconf, Validator

_PACKAGE_ROOT = Path(__file__).resolve().parent.parent


def _build_validators() -> list[Validator]:
    """Construct a fresh set of validators. Returns new instances each call so they
    can be registered with multiple Dynaconf instances (validators carry state).
    """
    return [
        Validator("ccr_follower.enabled", is_type_of=bool, must_exist=True),
        Validator("ccr_follower.url", is_type_of=str, len_min=1, must_exist=True),
        Validator("ccr_follower.api_key", is_type_of=str, must_exist=True),
        Validator(
            "ccr_follower.request_timeout_sec",
            is_type_of=(int, float),
            gt=0,
            must_exist=True,
        ),
        Validator("ccr_follower.interval_sec", is_type_of=(int, float), gt=0, must_exist=True),
        Validator("ccr_follower.index_patterns", is_type_of=list, len_min=1, must_exist=True),
        Validator(
            "logging.format",
            is_in=["mozlog", "pretty"],
            must_exist=True,
        ),
        Validator(
            "logging.level",
            is_in=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
            must_exist=True,
        ),
        Validator("logging.can_propagate", is_type_of=bool, must_exist=True),
        Validator(
            "sentry.mode",
            is_in=["disabled", "release", "debug"],
            must_exist=True,
        ),
        Validator("sentry.env", is_in=["prod", "stage", "dev"], must_exist=True),
        Validator("sentry.dsn", is_type_of=str, must_exist=True),
        Validator(
            "sentry.traces_sample_rate",
            is_type_of=float,
            gte=0,
            lte=1,
            must_exist=True,
        ),
    ]


# `root_path` resolves settings_files relative to the merino_hook_eye package.
# `envvar_prefix` exports envvars as `MERINO_HOOK_EYE_FOO=bar`.
# `env_switcher` selects environment via `MERINO_HOOK_EYE_ENV=production`.
# Default: `development`.
settings = Dynaconf(
    root_path=str(_PACKAGE_ROOT),
    envvar_prefix="MERINO_HOOK_EYE",
    settings_files=[
        "configs/default.toml",
        "configs/development.toml",
        "configs/production.toml",
        "configs/stage.toml",
        "configs/testing.toml",
    ],
    environments=True,
    env_switcher="MERINO_HOOK_EYE_ENV",
    validators=_build_validators(),
)

settings.validators.validate()
