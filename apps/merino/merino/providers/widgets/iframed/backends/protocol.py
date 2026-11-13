"""Protocol for iframed widgets backend."""

import datetime

from pydantic import BaseModel, Field, HttpUrl


class FramedWidget(BaseModel):
    """Common properties for modeling a framed widget. Extended for a GCS monitoring and API response."""

    enabled: bool = Field(description="Instruct New Tab whether or not to show the widget.")
    id: str = Field(
        description="Identifier for the widget. Must match the source of truth - New Tab widget registry."
    )
    vendor: str = Field(
        description="Vendor supplying the widget, e.g. 'Yahoo'. Use 'Mozilla' for internal widgets."
    )


class FramedWidgetGCS(FramedWidget):
    """Model for monitoring a framed widget in GCS."""

    bucket_name: str = Field(description="The GCS bucket name.")
    cdn_host: str = Field(description="CDN hostname for the bucket.")


class FramedWidgetResponse(FramedWidget):
    """Model for a single framed widget for API response."""

    url: HttpUrl = Field(
        description="URL of the widget. Should be a GCP load balancer URL or equivalent."
    )


class FramedWidgetsApiResponse(BaseModel):
    """Model for the full API response."""

    date_utc: datetime.datetime = Field(description="The UTC datetime the response was sent.")
    locale: str = Field(
        description="The locale requested by the client. In the future may filter the widget result set."
    )
    widgets: list[FramedWidgetResponse] = Field(
        description="The list of available framed widgets."
    )
