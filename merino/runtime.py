"""Runtime mode helpers for selecting Merino feature groups."""

from enum import StrEnum


class RuntimeFeature(StrEnum):
    """Feature groups controlled by the runtime mode."""

    REGULAR_API = "regular_api"
    WCS_API = "wcs_api"


class RuntimeMode(StrEnum):
    """Boot-time runtime profiles for Merino."""

    ALL = "ALL"
    REGULAR = "REGULAR"
    WIDGET = "WIDGET"


_ALLOWED_RUNTIME_MODES = ", ".join(mode.value for mode in RuntimeMode)

_RUNTIME_MODE_FEATURES: dict[RuntimeMode, frozenset[RuntimeFeature]] = {
    RuntimeMode.ALL: frozenset({RuntimeFeature.REGULAR_API, RuntimeFeature.WCS_API}),
    RuntimeMode.REGULAR: frozenset({RuntimeFeature.REGULAR_API}),
    RuntimeMode.WIDGET: frozenset({RuntimeFeature.WCS_API}),
}


def coerce_runtime_mode(value: RuntimeMode | str | None) -> RuntimeMode:
    """Return a runtime mode for a config or test value."""
    if isinstance(value, RuntimeMode):
        return value
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"runtime mode must be set to one of: {_ALLOWED_RUNTIME_MODES}")
    try:
        return RuntimeMode(value)
    except ValueError as exc:
        raise ValueError(f"runtime mode must be one of: {_ALLOWED_RUNTIME_MODES}") from exc


def get_runtime_mode() -> RuntimeMode:
    """Return the runtime mode configured for this process."""
    from merino.configs import settings

    return coerce_runtime_mode(settings.runtime.mode)


def mode_features(mode: RuntimeMode | str | None) -> frozenset[RuntimeFeature]:
    """Return the feature groups enabled for a runtime mode."""
    return _RUNTIME_MODE_FEATURES[coerce_runtime_mode(mode)]


def mode_enables(mode: RuntimeMode | str | None, feature: RuntimeFeature) -> bool:
    """Return whether a runtime mode enables a feature group."""
    return feature in mode_features(mode)
