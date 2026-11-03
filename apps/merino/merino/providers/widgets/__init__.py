"""Initialize widget providers."""

from merino.configs import settings
from merino.providers.widgets.wrexham.provider import WrexhamProvider
from merino.providers.widgets.iframed.provider import Provider as IframedWidgetsProvider
from merino.utils.metrics import get_metrics_client

_wrexham_provider: WrexhamProvider | None = None
_wrexham_mock_data_enabled = settings.widgets.providers.wrexham.mock_data_enabled

_iframed_widgets_provider: IframedWidgetsProvider | None = None
_iframed_widgets_provider_enabled = settings.widget_providers.iframed.enabled


async def init_providers() -> None:
    """Initialize widget providers."""
    init_wrexham_provider()
    init_widget_provider()


def init_wrexham_provider() -> None:
    """Initialize the Wrexham widget provider."""
    global _wrexham_provider

    _wrexham_provider = WrexhamProvider(mock_data_enabled=_wrexham_mock_data_enabled)


async def shutdown_providers() -> None:
    """Shut down widget providers.

    This should only be called once at the shutdown of the application.
    """
    global _wrexham_provider

    if _wrexham_provider is not None:
        await _wrexham_provider.shutdown()
        _wrexham_provider = None


def get_wrexham_provider() -> WrexhamProvider:
    """Return the Wrexham widget provider."""
    if _wrexham_provider is None:
        raise ValueError("Wrexham widget provider has not been initialized.")

    return _wrexham_provider


def init_widget_provider() -> None:
    """Initialize the iframed widgets provider."""
    global _iframed_widgets_provider

    _iframed_widgets_provider = IframedWidgetsProvider(
        metrics_client=get_metrics_client(),
        name="iframed Widgets Provider",
        enabled=_iframed_widgets_provider_enabled,
    )


def get_iframed_widgets_provider() -> IframedWidgetsProvider:
    """Return the iframed widgets provider"""
    if _iframed_widgets_provider is None:
        raise ValueError("iframed widgets provider has not been initialized.")

    return _iframed_widgets_provider
