"""Base Models for New Tab code."""
from pydantic import BaseModel, Field


class Recommendation(BaseModel):
    """The Recommendation object in the same format as what Pocket returns.
    For more about the original definition: please consult the types
    (here)[https://github.com/Pocket/firefox-api-proxy/blob/598d2d8fabb5bad874f484ee04d73f0eb266bb43/src/generated/openapi/types.ts#L98].
    """

    typename: str = Field(
        default="Recommendation",
        description="Constant identifier for Recommendation type objects.",
        serialization_alias="__typename",
    )
    url: str = Field(description="The URL the Recommendation.")
    title: str = Field(description="The title of the Recommendation.")
    excerpt: str = Field(description="An excerpt from the Recommendation.")
    publisher: str | None = Field(description="The publisher of the Recommendation.")
    image_url: str = Field(
        description="The primary image for a Recommendation.",
        serialization_alias="imageUrl",
    )
    tile_id: int | None = Field(
        default=None,
        description="Pocket specific and not used. Keeping this in the model for reference."
        "Numerical identifier for the Recommendation. "
        "This is specifically a number for Fx client and Mozilla data pipeline compatibility. "
        "This property will continue to be present because Firefox clients depend on it, "
        "but downstream users should use the recommendation id instead when available.",
        serialization_alias="tileId",
    )
    time_to_read: int | None = Field(
        default=None,
        description="Pocket specific and not used. Keeping this in the model for reference."
        "Article read time in minutes",
        serialization_alias="timeToRead",
    )
    recommendation_id: str | None = Field(
        default=None,
        description="Pocket specific and not used. Keeping this in the model for reference. "
        "String identifier for the Recommendation. "
        "This value is expected to be different on each request.",
        serialization_alias="recommendationId",
    )
