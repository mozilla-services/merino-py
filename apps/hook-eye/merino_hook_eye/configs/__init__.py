"""Configuration for merino-hook-eye."""

from pathlib import Path
from urllib.parse import urlsplit

from dynaconf import Dynaconf, Validator

_PACKAGE_ROOT = Path(__file__).resolve().parent.parent


def _is_https(url: object) -> bool:
    """Return whether `url` is a string with an `https` scheme."""
    return isinstance(url, str) and urlsplit(url).scheme.lower() == "https"


def _follower_on() -> Validator:
    """Return a new validator that passes only when the CCR follower check is enabled."""
    return Validator("ccr_follower.enabled", eq=True)


def _build_validators() -> list[Validator]:
    """Construct a fresh set of validators. Returns new instances each call so they
    can be registered with multiple Dynaconf instances (validators carry state).
    """
    return [
        Validator("ccr_follower.enabled", is_type_of=bool, must_exist=True),
        # The other settings are only checked, and only required, when the check runs.
        Validator(
            "ccr_follower.url", is_type_of=str, len_min=1, must_exist=True, when=_follower_on()
        ),
        Validator("ccr_follower.api_key", is_type_of=str, must_exist=True, when=_follower_on()),
        # The client sends the API key in the `Authorization` header, so it must not travel over
        # plaintext HTTP. Keyless `http://` URLs stay allowed for local clusters.
        Validator(
            "ccr_follower.url",
            condition=_is_https,
            when=_follower_on() & Validator("ccr_follower.api_key", len_min=1),
            messages={
                "condition": (
                    "{name} must use https:// when ccr_follower.api_key is set, but it is"
                    " {value} in env {env}"
                )
            },
        ),
        Validator(
            "ccr_follower.request_timeout_sec",
            is_type_of=(int, float),
            gt=0,
            must_exist=True,
            when=_follower_on(),
        ),
        Validator(
            "ccr_follower.interval_sec",
            is_type_of=(int, float),
            gt=0,
            must_exist=True,
            when=_follower_on(),
        ),
        Validator(
            "ccr_follower.index_patterns",
            is_type_of=list,
            len_min=1,
            must_exist=True,
            when=_follower_on(),
        ),
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
