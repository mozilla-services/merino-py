"""Framed widgets provider module that contains logic and methods to return all framed widgets."""

import asyncio
import datetime
import logging
import time

from typing import Any
from pydantic import HttpUrl

import aiodogstatsd

from merino_common.utils import cron

from merino.configs import settings
from merino.providers.widgets.iframed.backends.protocol import (
    FramedWidgetResponse,
    FramedWidgetsApiResponse,
)
from merino.providers.widgets.iframed.backends.framed import FramedWidgetsBackend

logger = logging.getLogger(__name__)


class Provider:
    """Provider for framed widgets."""

    cron_task: asyncio.Task | None
    last_fetch_at: float
    metrics_client: aiodogstatsd.Client
    widgets_response: list[FramedWidgetResponse]

    def __init__(
        self,
        # the backend will be None if the GCS client fails to initialize
        backend: FramedWidgetsBackend | None,
        cron_interval_sec: float,
        metrics_client: aiodogstatsd.Client,
        name: str,
        resync_interval_sec: float,
        cron_enabled: bool = False,
        enabled: bool = False,
        **kwargs: Any,
    ) -> None:
        self.backend = backend
        self.cron_interval_sec = cron_interval_sec
        self.metrics_client = metrics_client
        self.name = name
        self.resync_interval_sec = resync_interval_sec
        self._cron_enabled = cron_enabled
        self._enabled = enabled

        # set instance defaults
        self.cron_task = None
        self.last_fetch_at = 0
        self.widgets_response = []

    async def initialize(self) -> None:
        """Initialize cron job."""
        if self._enabled and self._cron_enabled:
            # Run a cron job that inspects GCS for the latest semver per widget.
            # Executes immediately, as last_fetch_at defaults to 0.
            cron_job = cron.Job(
                name="refresh_framed_widgets",
                interval=self.cron_interval_sec,
                condition=self._should_fetch,
                task=self._fetch,
            )

            # Store the created task on the instance variable. Otherwise it will get
            # garbage collected because asyncio's runtime only holds a weak
            # reference to it.
            self.cron_task = asyncio.create_task(cron_job())

    def shutdown(self) -> None:
        """Shutdown the cron task if it's running."""
        if self.cron_task is not None:
            _ = self.cron_task.cancel()
            self.cron_task = None

    def _should_fetch(self) -> bool:
        """Check if it's time to inspect GCS for new widget releases."""
        return (time.time() - self.last_fetch_at) >= self.resync_interval_sec

    async def _fetch(self) -> None:
        """Fetch latest framed widget releases."""
        # if the GCS client failed to initialize, we can't fetch.
        # note that this is a redundant check given how the provider is
        # initialized, but it's worthwhile here to make intention clear.
        if self.backend is None:  # pragma: no cover
            return

        self.widgets_response = await self.backend.fetch()
        self.last_fetch_at = time.time()

    async def get_widgets(self, locale: str) -> FramedWidgetsApiResponse:
        """Return hard-coded widgets until we set up GCS monitoring."""
        response = FramedWidgetsApiResponse(
            date_utc=datetime.datetime.now(datetime.timezone.utc), locale=locale, widgets=[]
        )

        # If the provider is not enabled, return response with no widget data.
        if not self._enabled:
            return response

        # TODO: replace with self.widgets_response when backend is completed
        # TODO: hard-code crossword result here, as it currently doesn't follow
        # the new pattern.
        response.widgets = Provider.fake_widget_manifest()

        return response

    @staticmethod
    def fake_widget_manifest() -> list[FramedWidgetResponse]:
        """Return hard-coded list of widgets. Used for testing."""
        if settings.current_env.lower() == "production":
            widgets = [
                FramedWidgetResponse(
                    id="crossword",
                    vendor="particle",
                    enabled=True,
                    url=HttpUrl(
                        "https://prod-games-particle.merino.prod.webservices.mozgcp.net/index.html"
                    ),
                ),
                FramedWidgetResponse(
                    id="horoscopes",
                    vendor="yahoo",
                    enabled=True,
                    url=HttpUrl(
                        "https://prod-widgets-yahoo-horoscope.merino.prod.webservices.mozgcp.net/1.3.20261112170617/index.html"
                    ),
                ),
                FramedWidgetResponse(
                    id="solitaire",
                    vendor="yahoo",
                    enabled=True,
                    url=HttpUrl(
                        "https://prod-widgets-yahoo-solitaire.merino.prod.webservices.mozgcp.net/1.3.20261112182920/index.html"
                    ),
                ),
                FramedWidgetResponse(
                    id="travel",
                    vendor="mozilla",
                    enabled=True,
                    url=HttpUrl(
                        "https://prod-widgets-kayak-travel.merino.prod.webservices.mozgcp.net/1.4.202611101753/index.html"
                    ),
                ),
                FramedWidgetResponse(
                    id="wrexhamAFC",
                    vendor="mozilla",
                    enabled=True,
                    url=HttpUrl(
                        "https://prod-widgets-wrexhamafc.merino.prod.webservices.mozgcp.net/1.1.202611092014/index.html"
                    ),
                ),
            ]
        else:
            widgets = [
                FramedWidgetResponse(
                    id="crossword",
                    vendor="particle",
                    enabled=True,
                    url=HttpUrl(
                        "https://stage-games-particle.merino.nonprod.webservices.mozgcp.net/index.html"
                    ),
                ),
                FramedWidgetResponse(
                    id="horoscopes",
                    vendor="yahoo",
                    enabled=True,
                    url=HttpUrl(
                        "https://stage-widgets-yahoo-horoscope.merino.nonprod.webservices.mozgcp.net/1.3.20261112170623/index.html"
                    ),
                ),
                FramedWidgetResponse(
                    id="solitaire",
                    vendor="yahoo",
                    enabled=True,
                    url=HttpUrl(
                        "https://stage-widgets-yahoo-solitaire.merino.nonprod.webservices.mozgcp.net/1.3.20261112181700/index.html"
                    ),
                ),
                FramedWidgetResponse(
                    id="travel",
                    vendor="mozilla",
                    enabled=True,
                    url=HttpUrl(
                        "https://stage-widgets-kayak-travel.merino.nonprod.webservices.mozgcp.net/1.4.202611101753/index.html"
                    ),
                ),
                FramedWidgetResponse(
                    id="wrexhamAFC",
                    vendor="mozilla",
                    enabled=True,
                    url=HttpUrl(
                        "https://stage-widgets-wrexhamafc.merino.nonprod.webservices.mozgcp.net/1.1.202611092014/index.html"
                    ),
                ),
            ]

        return widgets
