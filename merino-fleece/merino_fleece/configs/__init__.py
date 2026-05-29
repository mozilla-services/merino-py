"""Configuration for merino-fleece."""

from pathlib import Path

from dynaconf import Dynaconf, Validator

_MERINO_FLEECE_PACKAGE_ROOT = Path(__file__).resolve().parent.parent

_ALLOWED_SPACY_MODELS = ["en_core_web_sm", "en_core_web_md", "en_core_web_lg"]


def _build_validators() -> list[Validator]:
    """Construct a fresh set of validators. Returns new instances each call so they
    can be registered with multiple Dynaconf instances (validators carry state).
    """
    return [
        Validator(
            "pii.model",
            is_type_of=str,
            is_in=_ALLOWED_SPACY_MODELS,
            must_exist=True,
        ),
        Validator(
            "pii.excluded_components",
            is_type_of=list,
            must_exist=True,
        ),
        Validator(
            "pii.query_character_max",
            is_type_of=int,
            gt=0,
            lte=500,
            must_exist=True,
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


# `root_path` resolves settings_files relative to the merino_fleece package.
# `envvar_prefix` exports envvars as `MERINO_FLEECE_FOO=bar`.
# `env_switcher` selects environment via `MERINO_FLEECE_ENV=production`. Default: `development`.
settings = Dynaconf(
    root_path=str(_MERINO_FLEECE_PACKAGE_ROOT),
    envvar_prefix="MERINO_FLEECE",
    settings_files=[
        "configs/default.toml",
        "configs/development.toml",
        "configs/production.toml",
        "configs/testing.toml",
    ],
    environments=True,
    env_switcher="MERINO_FLEECE_ENV",
    validators=_build_validators(),
)

settings.validators.validate()
