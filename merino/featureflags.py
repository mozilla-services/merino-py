import hashlib
from contextvars import ContextVar
from random import randbytes
from typing import cast

from dynaconf import Dynaconf

_flags = Dynaconf(
    root_path="merino",
    envvar_prefix="MERINO_FLAGS",
    settings_files=[
        "configs/flags.toml",
    ],
    environments=True,
    env_switcher="MERINO_ENV",
)

session_id_context: ContextVar[str | None] = ContextVar("session_id", default=None)


class FeatureFlags:
    flags: dict

    def __init__(self, flags: dict | None = None) -> None:
        self.flags = (flags if flags is not None else _flags).get("flags", {})

    def is_enabled(self, flag: str, bucket_for: str | bytes | None = None) -> bool:
        config = self.flags.get(flag)
        if config is None:
            return False

        enabled = config.get("enabled", 0.0)
        # enabled should be gt 0 and lt 1
        if enabled <= 0.0 or enabled > 1.0:
            return False

        # override bucketing id if specified in args
        bucketing_id: bytes = bytes()
        if bucket_for is not None:
            bucket_type = type(bucket_for)
            if bucket_type is str:
                bucketing_id = self._get_digest(cast(str, bucket_for))
            elif bucket_type is bytes:
                bucketing_id = cast(bytes, bucket_for)
        else:
            match config.get("scheme"):
                case "random":
                    bucketing_id = self._get_random()
                case "session" if (session_id := session_id_context.get()) is not None:
                    bucketing_id = self._get_digest(session_id)
                case _:  # Only currently supporting 'random' as a bucketing scheme
                    return False

        bucket_value = self._bytes_to_interval(bucketing_id)
        return bucket_value <= enabled

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
