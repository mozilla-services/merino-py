import hashlib
from random import randbytes

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


class FeatureFlags:
    flags: dict

    def __init__(self, flags: dict | None = None) -> None:
        if flags is not None:
            self.flags = flags
        else:
            self.flags = _flags.get("flags", {})

    def is_enabled(self, flag: str, bucket_for: str | None = None) -> bool:
        config = self.flags.get(flag)
        if config is None:
            return False

        enabled = config.get("enabled", 0.0)
        # enabled should be gt 0 and lt 1
        if enabled <= 0.0 or enabled > 1.0:
            return False

        bucketing_id: bytes
        # override bucketing id if specified in args
        if bucket_for is not None:
            bucketing_id = self._get_digest(bucket_for)
        match config.get("bucketing"):
            case "random":
                bucketing_id = self._get_random()
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
        size = len(bucketing_id)  # this should always be 32 bytes long
        for i in bucketing_id:
            bit = 0 if i < 128 else 1
            out = (out << 1) + bit
        return out / size


flags = FeatureFlags()
