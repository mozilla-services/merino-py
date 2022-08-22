import hashlib
from contextvars import ContextVar
from random import randbytes
from typing import cast

from dynaconf import Dynaconf, Validator


_flags = Dynaconf(
    root_path="merino",
    envvar_prefix="MERINO",
    settings_files=[
        "configs/flags/default.toml",
        "configs/flags/testing.toml",
    ],
    validators=[
        Validator(r"flags\.\w+\.enabled", gt=0.0, lte=1.0),
        Validator(r"flags\.\w+\.scheme", is_in=["random", "session"]),
    ],
    environments=True,
    env_switcher="MERINO_ENV",
)

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

    Each flag has a very simple configuration:

    ```
    [default.flags.<flag_name>]
    scheme = 'session'
    enabled = 0.5
    ```

    `scheme` - This is the bucketing scheme for the flag. Allowed values are 'random' and 'session'
    `enabled` - This represents the % enabled for the flag and must be a float between 0 and 1
    """
    flags: dict

    def __init__(self) -> None:
        self.flags = _flags.get("flags", {})

    def is_enabled(self, flag: str, bucket_for: str | bytes | None = None) -> bool:
        """
        Checks if a given flag is enabled via a feature flag configuration block.
        As a principal it fails closed as quickly as possible.
        """
        config = self.flags.get(flag)
        if config is None:
            return False

        enabled = config.get("enabled", 0.0)
        # enabled should be gt 0 and lt 1
        if enabled <= 0.0 or enabled > 1.0:
            return False

        bucket_scheme = config.get("scheme")
        if (bucketing_id := self._get_bucketing_id(bucket_scheme, bucket_for)) is None:
            return False

        bucket_value = self._bytes_to_interval(bucketing_id)
        return bucket_value <= enabled

    def _get_bucketing_id(
        self, scheme: str, bucket_for: str | bytes | None
    ) -> bytes | None:
        # override bucketing id if specified in args
        if bucket_for is not None:
            bucket_type = type(bucket_for)
            if bucket_type is str:
                return self._get_digest(cast(str, bucket_for))
            elif bucket_type is bytes:
                return cast(bytes, bucket_for)
        else:
            # Otherwise use the scheme specified in the config
            match scheme:
                case "random":
                    return self._get_random()
                case "session" if (session_id := session_id_context.get()) is not None:
                    return self._get_digest(session_id)
                case _:
                    return None

    def _get_random(self) -> bytes:
        return randbytes(32)

    def _get_digest(self, id: str) -> bytes:
        hash = hashlib.sha256(bytes(id, "utf-8"))
        return hash.digest()

    def _bytes_to_interval(self, bucketing_id: bytes) -> float:
        out = 0
        max = 1 << len(bucketing_id)  # this should always be 32 bytes long
        for i in bucketing_id:
            bit = 0 if i < 128 else 1
            out = (out << 1) + bit
        return out / max
