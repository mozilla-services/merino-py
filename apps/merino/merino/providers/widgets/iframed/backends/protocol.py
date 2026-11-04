"""Protocol for iframed widgets backend."""

import datetime

from pydantic import BaseModel, Field, HttpUrl


class IframedWidget(BaseModel):
    """Model for an iframed widget"""

    enabled: bool = Field(description="Instruct New Tab whether or not to show the widget.")
    id: str = Field(
        description="Identifier for the widget. Must match the source of truth - New Tab widget registry."
    )
    url: HttpUrl = Field(
        description="URL of the widget. Should be a GCP load balancer URL or equivalent."
    )
    vendor: str = Field(
        description="Vendor supplying the widget, e.g. 'Yahoo'. Use 'Mozilla' for internal widgets."
    )


class IframedWidgetsResponse(BaseModel):
    """Model for an iframed widget response."""

    date_utc: datetime.datetime = Field(description="The UTC datetime the response was sent.")
    locale: str = Field(
        description="The locale requested by the client. In the future may filter the widget result set."
    )
    widgets: list[IframedWidget] = Field(description="The list of available iframed widgets.")
