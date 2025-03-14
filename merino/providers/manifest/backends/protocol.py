"""Protocol for the Manifest provider backend."""

from enum import Enum
from typing import Optional, Protocol

from pydantic import BaseModel, HttpUrl
from merino.exceptions import BackendError


class ManifestBackendError(BackendError):
    """Manifest Specific Errors"""

    pass


class GetManifestResultCode(Enum):
    """Enum to capture the result of getting manifest file."""

    SUCCESS = 0
    FAIL = 1
    SKIP = 2


class Domain(BaseModel):
    """Model for a domain within a manifest."""

    rank: int
    domain: str
    categories: list[str]
    serp_categories: list[int]
    url: HttpUrl
    title: str
    icon: str


class ManifestData(BaseModel):
    """Model for manifest file content"""

    domains: list[Domain]
    partners: Optional[
        list[dict[str, str]]
    ] = []  # TODO remove Optional tag after first successful job run with partners field


class ManifestBackend(Protocol):
    """Protocol for the Manifest backend that the provider depends on."""

    async def fetch(self) -> tuple[GetManifestResultCode, ManifestData | None]:
        """Fetch the manifest from storage and return it as a tuple.
        Returns:
            A tuple of (GetManifestResultCode, dict or None)
        Raises:
            ManifestBackendError: If the manifest is unavailable or there is an error reading it.
        """
        ...
