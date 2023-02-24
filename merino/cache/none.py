"""No-operation adapter that disables caching."""

from datetime import timedelta
from typing import Optional, Union


class NoCacheAdapter:  # pragma: no cover
    """A cache adapter that doesn't store or return anything."""

    async def get(self, key: str) -> Optional[bytes]:  # noqa: D102
        return None

    async def set(
        self,
        key: str,
        value: Union[bytes, str],
        ttl: Optional[timedelta] = None,
    ) -> None:  # noqa: D102
        pass

    async def close(self) -> None:  # noqa: D102
        pass
