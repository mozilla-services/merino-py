"""Initialize widget providers."""

from merino.configs import settings
from merino.providers.widgets.wrexham.provider import WrexhamProvider

_wrexham_provider: WrexhamProvider | None = None

_wrexham_mock_data_enabled = settings.widgets.providers.wrexham.mock_data_enabled


async def init_providers() -> None:
    """Initialize widget providers - currently only Wrexham AFC."""
    init_wrexham_provider()


def init_wrexham_provider() -> None:
    """Initialize the Wrexham widget provider."""
    global _wrexham_provider

    _wrexham_provider = WrexhamProvider(mock_data_enabled=_wrexham_mock_data_enabled)


def get_wrexham_provider() -> WrexhamProvider:
    """Return the Wrexham widget provider."""
    if _wrexham_provider is None:
        raise ValueError("Wrexham widget provider has not been initialized.")

    return _wrexham_provider
