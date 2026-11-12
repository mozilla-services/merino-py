"""iframed widgets provider module that contains logic and methods to return all iframed widgets."""

import datetime
from typing import Any

import aiodogstatsd
from pydantic import HttpUrl

from merino.configs import settings
from merino.providers.widgets.iframed.backends.protocol import (
    IframedWidget,
    IframedWidgetsResponse,
)


class Provider:
    """Provider for iframed widgets."""

    metrics_client: aiodogstatsd.Client

    def __init__(
        self,
        metrics_client: aiodogstatsd.Client,
        name: str,
        enabled: bool = False,
        **kwargs: Any,
    ) -> None:
        self.metrics_client = metrics_client
        self.name = name
        self._enabled = enabled

    async def get_widgets(self, locale: str) -> IframedWidgetsResponse:
        """Return hard-coded widgets until we set up GCS monitoring."""
        response = IframedWidgetsResponse(
            date_utc=datetime.datetime.now(datetime.timezone.utc), locale=locale, widgets=[]
        )

        if not self._enabled:
            return response

        # hard-coded until we set up GCS inspection
        if settings.current_env.lower() == "production":
            widgets = [
                IframedWidget(
                    id="crossword",
                    vendor="particle",
                    enabled=True,
                    url=HttpUrl(
                        "https://prod-games-particle.merino.prod.webservices.mozgcp.net/index.html"
                    ),
                ),
                IframedWidget(
                    id="horoscopes",
                    vendor="yahoo",
                    enabled=True,
                    url=HttpUrl(
                        "https://prod-widgets-yahoo-horoscope.merino.prod.webservices.mozgcp.net/1.3.20261112170617/index.html"
                    ),
                ),
                IframedWidget(
                    id="solitaire",
                    vendor="yahoo",
                    enabled=True,
                    url=HttpUrl(
                        "https://prod-widgets-yahoo-solitaire.merino.prod.webservices.mozgcp.net/1.3.20261112182920/index.html"
                    ),
                ),
                IframedWidget(
                    id="travel",
                    vendor="mozilla",
                    enabled=True,
                    url=HttpUrl(
                        "https://prod-widgets-kayak-travel.merino.prod.webservices.mozgcp.net/1.4.202611101753/index.html"
                    ),
                ),
                IframedWidget(
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
                IframedWidget(
                    id="crossword",
                    vendor="particle",
                    enabled=True,
                    url=HttpUrl(
                        "https://stage-games-particle.merino.nonprod.webservices.mozgcp.net/index.html"
                    ),
                ),
                IframedWidget(
                    id="horoscopes",
                    vendor="yahoo",
                    enabled=True,
                    url=HttpUrl(
                        "https://stage-widgets-yahoo-horoscope.merino.nonprod.webservices.mozgcp.net/1.3.20261112170623/index.html"
                    ),
                ),
                IframedWidget(
                    id="solitaire",
                    vendor="yahoo",
                    enabled=True,
                    url=HttpUrl(
                        "https://stage-widgets-yahoo-solitaire.merino.nonprod.webservices.mozgcp.net/1.3.20261112181700/index.html"
                    ),
                ),
                IframedWidget(
                    id="travel",
                    vendor="mozilla",
                    enabled=True,
                    url=HttpUrl(
                        "https://stage-widgets-kayak-travel.merino.nonprod.webservices.mozgcp.net/1.4.202611101753/index.html"
                    ),
                ),
                IframedWidget(
                    id="wrexhamAFC",
                    vendor="mozilla",
                    enabled=True,
                    url=HttpUrl(
                        "https://stage-widgets-wrexhamafc.merino.nonprod.webservices.mozgcp.net/1.1.202611092014/index.html"
                    ),
                ),
            ]

        response.widgets = widgets

        return response
