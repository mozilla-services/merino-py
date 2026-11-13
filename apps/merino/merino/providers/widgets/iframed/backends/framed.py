"""Framed Widgets backend."""

import logging
import aiodogstatsd
from pydantic import HttpUrl

from google.cloud.storage import Client

from merino.providers.widgets.iframed.backends.protocol import (
    FramedWidgetResponse,
    FramedWidgetGCS,
)
from merino.providers.widgets.iframed.backends.widgets_manifest import build_manifest

logger = logging.getLogger(__name__)


class FramedWidgetsBackend:
    """Backend for fetching the latest release URLs for all framed widgets."""

    gcs_client: Client
    metrics_client: aiodogstatsd.Client
    widgets_manifest: list[FramedWidgetGCS]

    def __init__(
        self,
        gcs_client: Client,
        metrics_client: aiodogstatsd.Client,
    ) -> None:
        """Initialize the backend."""
        self.gcs_client = gcs_client
        self.metrics_client = metrics_client
        self.widgets_manifest = build_manifest()

    async def fetch(self) -> list[FramedWidgetResponse]:
        """Fetch framed widget data from GCS."""
        response = []

        # TODO: update loop below to handle individual widget failures, and
        # gather up async tasks with task_runner
        for widget in self.widgets_manifest:
            # get the latest semver from GCS
            semver = await self._get_latest_release_for_widget(widget.bucket_name)

            # build the public URL
            url = FramedWidgetsBackend.build_semver_url(widget.cdn_host, semver)

            # construct the API response for this widget
            widget_response = FramedWidgetResponse(
                enabled=widget.enabled, id=widget.id, vendor=widget.vendor, url=url
            )

            response.append(widget_response)

        return response

    # TODO: add retry decorator
    async def _get_latest_release_for_widget(self, bucket_name: str) -> str:
        """Return latest sermver release from the given GCS bucket_name."""
        # TODO: call GCS and determine/return latest semver folder
        return "1.0.test"

    @staticmethod
    def build_semver_url(cdn_host: str, semver: str) -> HttpUrl:
        """Construct a URL for the given semver folder."""
        return HttpUrl(f"https://{cdn_host}/{semver}/index.html")
