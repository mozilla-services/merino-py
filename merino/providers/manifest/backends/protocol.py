"""Protocol for the Manifest provider backend."""

from typing import Any, Protocol
from merino.exceptions import BackendError
from merino.providers.manifest.backends.filemanager import GetManifestResultCode


class ManifestBackendError(BackendError):
    """Manifest Specific Errors"""

    pass


class ManifestBackend(Protocol):
    """Protocol for the Manifest backend that the provider depends on."""

    async def fetch(self) -> tuple[GetManifestResultCode, dict[str, Any] | None]:
        """Fetch the manifest from storage and return it as a tuple.

        Returns:
            A tuple of (GetManifestResultCode, dict or None)

        Raises:
            BackendError: If the manifest is unavailable or there is an error reading it.
        """
        ...
