"""Manifest of all Framed Widgets."""

from merino.configs import settings

from merino.providers.widgets.iframed.backends.protocol import (
    FramedWidgetGCS,
)

# this manifest must be manually updated when a framed widget is added or removed.


def build_manifest() -> list[FramedWidgetGCS]:
    """Build the manifest of framed widgets."""
    _bucket_name_kayak_travel = settings.widgets.providers.framed.bucket_name_kayak_travel
    _bucket_name_wrexhamafc = settings.widgets.providers.framed.bucket_name_wrexhamafc
    _bucket_name_yahoo_horoscope = settings.widgets.providers.framed.bucket_name_yahoo_horoscope
    _bucket_name_yahoo_solitaire = settings.widgets.providers.framed.bucket_name_yahoo_solitaire
    _cdn_host_kayak_travel = settings.widgets.providers.framed.cdn_hostname_kayak_travel
    _cdn_host_wrexhamafc = settings.widgets.providers.framed.cdn_hostname_wrexhamafc
    _cdn_host_yahoo_horoscope = settings.widgets.providers.framed.cdn_hostname_yahoo_horoscope
    _cdn_host_yahoo_solitaire = settings.widgets.providers.framed.cdn_hostname_yahoo_solitaire

    widgets: list[FramedWidgetGCS] = []

    # double check settings values before adding the widget to the manifest
    if _bucket_name_kayak_travel != "" and _cdn_host_kayak_travel != "":
        widgets.append(
            FramedWidgetGCS(
                bucket_name=_bucket_name_kayak_travel,
                cdn_host=_cdn_host_kayak_travel,
                enabled=True,
                id="travel",
                vendor="mozilla",
            )
        )

    if _bucket_name_wrexhamafc != "" and _cdn_host_wrexhamafc != "":
        widgets.append(
            FramedWidgetGCS(
                bucket_name=_bucket_name_wrexhamafc,
                cdn_host=_cdn_host_wrexhamafc,
                enabled=True,
                id="wrexhamAFC",
                vendor="mozilla",
            )
        )

    if _bucket_name_yahoo_horoscope != "" and _cdn_host_yahoo_horoscope != "":
        widgets.append(
            FramedWidgetGCS(
                bucket_name=_bucket_name_yahoo_horoscope,
                cdn_host=_cdn_host_yahoo_horoscope,
                enabled=True,
                id="horoscopes",
                vendor="yahoo",
            )
        )

    if _bucket_name_yahoo_solitaire != "" and _cdn_host_yahoo_solitaire != "":
        widgets.append(
            FramedWidgetGCS(
                bucket_name=_bucket_name_yahoo_solitaire,
                cdn_host=_cdn_host_yahoo_solitaire,
                enabled=True,
                id="solitaire",
                vendor="yahoo",
            )
        )

    return widgets
