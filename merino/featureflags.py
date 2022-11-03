"""Implementation of Feature Flags (feature toggles) for Merino"""
import hashlib
import logging
from contextvars import ContextVar
from enum import Enum
from random import randbytes
from typing import Any, Callable

from dynaconf import Dynaconf
from pydantic import BaseModel, ConstrainedFloat, parse_obj_as
from pydantic.types import OptionalIntFloat
from wrapt import decorator

logger = logging.getLogger(__name__)


def _dynaconf_loader() -> Any:
    """Load configuration from disk using dynaconf."""
    return Dynaconf(
        root_path="merino",
        envvar_prefix="MERINO",
        settings_files=[
            "configs/flags/default.toml",
            "configs/flags/testing.toml",
        ],
        environments=True,
        env_switcher="MERINO_ENV",
    ).get("flags", {})


class Enabled(ConstrainedFloat):
    """Constrained float for the enabled state of a feature flag."""

    ge: OptionalIntFloat = 0.0
    le: OptionalIntFloat = 1.0


class BucketingScheme(str, Enum):
    """Enum for accepted feature flag bucketing schemes."""

    random = "random"
    session = "session"


class FeatureFlag(BaseModel):
    """Model representing a feature flag."""

    enabled: Enabled
    scheme: BucketingScheme = BucketingScheme.session


# Type aliases for feature flags
FeatureFlagsConfigurations = dict[str, FeatureFlag]
FeatureFlagsDecisions = dict[str, bool]

# Load the dynaconf configuration and parse it into pydantic models once and
# then use it as the default value for `flags` in `FeatureFlags`.
_DYNACONF_FLAGS = parse_obj_as(FeatureFlagsConfigurations, _dynaconf_loader())


@decorator
def record_decision(
    wrapped_method: Callable[..., bool],
    instance: "FeatureFlags",
    args: tuple,
    kwargs: dict,
) -> bool:
    """Record the decision for when is_enabled() is called for a feature flag."""
    # `flag_name` is expected to be the first positional argument
    [flag_name, *remaining_args] = args

    if flag_name in instance.decisions:
        # There has been a previous call to `is_enabled()` for this feature flag
        # name. Return the recorded decision rather than generating a new one.
        return instance.decisions[flag_name]

    # Call the decorated callable with the given arguments
    decision = wrapped_method(flag_name, *remaining_args, **kwargs)

    instance.decisions[flag_name] = decision
    logger.info(
        f"Record feature flag decision for {flag_name}", extra={flag_name: decision}
    )

    return decision


# The session ID is set on this context variable by the FeatureFlagsMiddleware
# based on the "sid" query parameter of an incoming HTTP request. We use that
# for feature flags using a "session" scheme.
session_id_context: ContextVar[str | None] = ContextVar("session_id", default=None)


class FeatureFlags:
    """Feature flags implementation using dynaconf as the configuration system.

    It supports two bucketing schemes `random` and `session`.

    Random does what it says on the tin. It generates a random bucketing id for
    every flag check. Session bucketing uses the session id of the request as
    the bucketing key so that feature checks within a given search session would
    be consistent.

    Additionally you can pass a custom bucketing_id via the `bucket_for`
    parameter. This is useful when you have an ad-hoc bucketing identifier that
    is not supported via one of the standard schemes.

    Each flag defines the following fields:

    ```
    [default.flags.<flag_name>]
    scheme = 'session'
    enabled = 0.5
    ```

    `scheme` - This is the bucketing scheme for the flag. Allowed values are 'random' and 'session'
    `enabled` - This represents the % enabled for the flag and must be a float between 0 and 1
    """

    flags: FeatureFlagsConfigurations
    decisions: FeatureFlagsDecisions

    def __init__(self, flags: dict | None = None) -> None:
        """Initialize feature flags."""
        if flags is None:
            self.flags = _DYNACONF_FLAGS
        else:
            self.flags = parse_obj_as(FeatureFlagsConfigurations, flags)

        # This dict is populated by @record_decision when is_enabled() is called
        self.decisions = {}

    @record_decision
    def is_enabled(self, flag_name: str, bucket_for: str | bytes | None = None) -> bool:
        """Check if a given flag is enabled via a feature flag configuration
        block. Two of the guiding principals for this method are: fail to 'off'
        as quickly as possible, and do not throw exceptions.

        Args:
            flag_name:
                Name of the feature flag. Should correspond to a `flags.<flag_name>` config block.
            bucket_for:
                An optional bucketing identifier. Useful for bucketing on a value that is
                not present in the currently supported bucket schemes.
        Returns:
            bool: Returns true if the feature should be enabled.
        """
        if flag_name not in self.flags:
            return False

        config = self.flags[flag_name]

        # Short circuits for enabled values of 0 or 1
        match config.enabled:
            case 0.0:
                return False
            case 1.0:
                return True

        try:
            bucketing_id = self._get_bucketing_id(config.scheme, bucket_for)
            bucket_value = self._bytes_to_interval(bucketing_id)
            return bucket_value <= config.enabled
        except (RuntimeError, TypeError, ValueError) as err:
            logger.exception(err)
            return False

    def _get_bucketing_id(
        self, scheme: BucketingScheme, bucket_for: str | bytes | None
    ) -> bytes:
        """Return a bytearray that can then be used to check against the
        enabled percent for inclusion into the feature.

        Args:
            scheme: The bucketing scheme. Can be `random` or `session`
            bucket_for:
                An optional bucketing id that will be used in place of the specified scheme.
                Can be either a string or bytes. If given a string we will create a digest
                using sha256.
        Returns:
            bytes
        Raises:
            TypeError, ValueError
        """
        # Override bucketing id if specified in args
        if bucket_for is not None:
            match bucket_for:
                case str():
                    return self._get_digest(bucket_for)
                case bytes():
                    return bucket_for
                case _:
                    raise TypeError(
                        f"bucketing_id: bucket_for must be str | bytes. got {type(bucket_for)}"
                    )
        else:
            # If bucket_for is None use the scheme specified in the config
            match scheme:
                case BucketingScheme.random:
                    return self._get_random()
                case BucketingScheme.session:
                    session_id = session_id_context.get()
                    if session_id is None:
                        raise ValueError(
                            "Expected a session_id but none exist in this context"
                        )
                    return self._get_digest(session_id)

    @staticmethod
    def _get_random() -> bytes:
        """Return bytearray with 32 random bytes."""
        return randbytes(32)

    @staticmethod
    def _get_digest(id: str) -> bytes:
        """Hash a string into a 32 byte bytearray."""
        hash = hashlib.sha256(bytes(id, "utf-8"))
        return hash.digest()

    @staticmethod
    def _bytes_to_interval(bucketing_id: bytes) -> float:
        """Take an arbitrarily long bytearray and maps it to a float between
        [0,1)
        """
        out = 0
        for byte in bucketing_id:
            out = (out << 1) + (byte >> 7)
        return out / (1 << len(bucketing_id))
