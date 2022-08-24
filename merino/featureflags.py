import hashlib
import logging
from collections.abc import Iterable
from contextvars import ContextVar
from enum import Enum
from random import randbytes
from typing import Optional

from dynaconf import Dynaconf
from pydantic import BaseModel, ConstrainedFloat
from pydantic.types import OptionalIntFloat

logger = logging.getLogger(__name__)


# Configuration and schema
def dynaconf_loader():
    return Dynaconf(
        root_path="merino",
        envvar_prefix="MERINO",
        settings_files=[
            "configs/flags/default.toml",
            "configs/flags/testing.toml",
        ],
        environments=True,
        env_switcher="MERINO_ENV",
    ).get("flags")


class Enabled(ConstrainedFloat):
    ge: OptionalIntFloat = 0.0
    le: OptionalIntFloat = 1.0


class Scheme(str, Enum):
    random = "random"
    session = "session"


class FeatureFlag(BaseModel):
    enabled: Enabled
    scheme: Optional[Scheme]


class FeatureFlagConfigs(BaseModel):

    flags: dict[str, Optional[FeatureFlag]]

    def __iter__(self) -> Iterable[str]:
        return iter(self.flags)

    def __getitem__(self, flag_name) -> FeatureFlag | None:
        return self.flags.get(flag_name, None)


_flags = FeatureFlagConfigs(flags=dynaconf_loader())


# The session ID is set on this context variable by the FeatureFlagsMiddleware
# based on the "sid" query parameter of an incoming HTTP request. We use that
# for feature flags using a "session" scheme.
session_id_context: ContextVar[str | None] = ContextVar("session_id", default=None)


class FeatureFlags:
    """
    A very basic implementation of featureflags using dynaconf as the configuration system.
    It supports two bucketing schemes `random` and `session`. Random does what it says on the tin.
    It generates a random bucketing id for every flag check. Session bucketing uses the session id
    of the request as the bucketing key so that feature checks within a given search session would
    be consistent. Additionally you can pass a custom bucketing_id via the `bucket_for` parameter.
    This is useful when you have an ad-hoc bucketing identifier that is not supported via one of
    the standard schemes.

    Each flag defines the following fields:

    ```
    [default.flags.<flag_name>]
    scheme = 'session'
    enabled = 0.5
    ```

    `scheme` - This is the bucketing scheme for the flag. Allowed values are 'random' and 'session'
    `enabled` - This represents the % enabled for the flag and must be a float between 0 and 1
    """

    flags: FeatureFlagConfigs
    default_scheme: str = "session"

    def __init__(self) -> None:
        self.flags = _flags

    def is_enabled(self, flag_name: str, bucket_for: str | bytes | None = None) -> bool:
        """
        Checks if a given flag is enabled via a feature flag configuration block.
        Two of the guiding principals for this method are: fail to 'off' as quickly as possible,
        and do not throw exceptions.

        Args:
            flag_name:
                Name of the feature flag. Should correspond to a `flags.<flag_name>` config block.
            bucket_for:
                An optional bucketing identifier. Useful for bucketing on a value that is
                not present in the currently supported bucket schemes.
        Returns:
            bool: Returns true if the feature should be enabled.

        """
        config = self.flags[flag_name]
        if config is None:
            return False

        enabled = config.enabled
        # enabled should be gt 0 and lt 1
        if enabled <= 0.0 or enabled > 1.0:
            return False

        bucket_scheme = config.scheme or self.default_scheme
        try:
            bucketing_id = self._get_bucketing_id(bucket_scheme, bucket_for)
            bucket_value = self._bytes_to_interval(bucketing_id)
            return bucket_value <= enabled
        except (RuntimeError, TypeError, ValueError) as err:
            logger.exception(err)
            return False

    def _get_bucketing_id(self, scheme: str, bucket_for: str | bytes | None) -> bytes:
        """
        Returns a bytearray that can then be used to check against the enabled percent
        for inclusion into the feature

        Args:
            scheme: The bucketing scheme. Can be `random` or `session`
            bucket_for:
                An optional bucketing id that will be used in place of the specified scheme.
                Can be either a string or bytes. If given a string we will create a digest
                using sha256.
        Returns:
            bytes
        Raises:
            RuntimeError
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
                case "random":
                    return self._get_random()
                case "session":
                    session_id = session_id_context.get()
                    if session_id is None:
                        raise ValueError(
                            "Expected a session_id but none exist in this context"
                        )
                    return self._get_digest(session_id)
                case _:
                    # This is now validated by the pydantic schema.
                    # However mypy complains about a None return type without this block.
                    raise RuntimeError(
                        f"bucketing_id: scheme must be on of `random`, `session`. got `{scheme}`"
                    )

    @staticmethod
    def _get_random() -> bytes:
        """
        Returns bytearray with 32 random bytes
        """
        return randbytes(32)

    @staticmethod
    def _get_digest(id: str) -> bytes:
        """
        Hashes a string into a 32 byte bytearray
        """
        hash = hashlib.sha256(bytes(id, "utf-8"))
        return hash.digest()

    @staticmethod
    def _bytes_to_interval(bucketing_id: bytes) -> float:
        """
        Takes an arbitrarily long bytearray and maps it to an float between [0,1)
        """
        out = 0
        for byte in bucketing_id:
            out = (out << 1) + (byte >> 7)
        return out / (1 << len(bucketing_id))
