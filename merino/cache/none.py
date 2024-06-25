"""No-operation adapter that disables caching."""

from datetime import timedelta
from typing import Any


class NoCacheAdapter:  # pragma: no cover
    """A cache adapter that doesn't store or return anything."""

    async def get(self, key: str) -> bytes | None:  # noqa: D102
        return None

    async def set(  # noqa: D102
        self,
        key: str,
        value: bytes | str,
        ttl: timedelta | None = None,
    ) -> None:
        pass

    async def close(self) -> None:  # noqa: D102
        pass

    def register_script(self, sid: str, script: str) -> None:  # noqa: D102
        pass

    async def run_script(self, sid: str, keys: list, args: list) -> Any:  # noqa: D102
        pass
