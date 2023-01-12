# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Load test models."""

from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Extra, Field, HttpUrl


class Suggestion(BaseModel, extra=Extra.allow):
    """Class that holds information about a Suggestion returned by Merino."""

    title: str
    url: HttpUrl
    provider: str
    is_sponsored: bool
    score: float
    icon: Optional[str]


class ResponseContent(BaseModel):
    """Class that contains suggestions and variants returned by Merino."""

    suggestions: List[Suggestion] = Field(default_factory=list)
    client_variants: List[str] = Field(default_factory=list)
    server_variants: List[str] = Field(default_factory=list)
    request_id: Optional[UUID] = Field(...)
