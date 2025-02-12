"""Curated Recommendations provider top-level request and response models"""

import hashlib
from enum import unique, Enum
from typing import Annotated, cast
import logging

from pydantic import Field, field_validator, model_validator, BaseModel, ValidationInfo

from merino.curated_recommendations.corpus_backends.protocol import CorpusItem, Topic
from merino.curated_recommendations.fakespot_backend.protocol import FakespotFeed

logger = logging.getLogger(__name__)


@unique
class TypeName(str, Enum):
    """This value could be used in the future to distinguish between different types of content.

    Currently, the only value is recommendation.
    """

    RECOMMENDATION = "recommendation"


@unique
class Locale(str, Enum):
    """Supported locales for curated recommendations on New Tab"""

    FR = ("fr",)
    FR_FR = ("fr-FR",)
    ES = ("es",)
    ES_ES = ("es-ES",)
    IT = ("it",)
    IT_IT = ("it-IT",)
    EN = ("en",)
    EN_CA = ("en-CA",)
    EN_GB = ("en-GB",)
    EN_US = ("en-US",)
    DE = ("de",)
    DE_DE = ("de-DE",)
    DE_AT = ("de-AT",)
    DE_CH = ("de-CH",)

    @staticmethod
    def values():
        """Map enum values & returns"""
        return Locale._value2member_map_


@unique
class ExperimentName(str, Enum):
    """List of Nimbus experiment names on New Tab. This list is NOT meant to be exhaustive.
    This is simply intended to make it easier to reference experiment names in this codebase,
    when Merino needs to change behavior depending on the experimentName request parameter.
    """

    # Experiment where high-engaging items scheduled for past dates are included.
    EXTENDED_EXPIRATION_EXPERIMENT = "new-tab-extend-content-duration"
    # Experiment where we apply a modified prior to reduce exploration
    MODIFIED_PRIOR_EXPERIMENT = "new-tab-feed-reduce-exploration"


# Maximum tileId that Firefox can support. Firefox uses Javascript to store this value. The max
# value of a Javascript number can be found using `Number.MAX_SAFE_INTEGER`. which is 2^53 - 1
# because it uses a 64-bit IEEE 754 float.
# Generate tile_ids well out of the range of the old MySQL-based system, which has a max tile_id of
# 99,999 as of 2023-03-13. This is done to make it easy for engineers/analysts to see which system
# generated the identifier.
MAX_TILE_ID = (1 << 53) - 1
MIN_TILE_ID = 10000000


class SectionConfiguration(BaseModel):
    """Configuration settings for a Section"""

    sectionId: str
    isFollowed: bool
    isBlocked: bool


class CuratedRecommendation(CorpusItem):
    """Extends CorpusItem with additional fields for a curated recommendation"""

    __typename: TypeName = TypeName.RECOMMENDATION
    tileId: Annotated[int, Field(strict=True, ge=MIN_TILE_ID, le=MAX_TILE_ID)]
    receivedRank: int

    @model_validator(mode="before")
    def set_tileId(cls, values):
        """Set the tileId field automatically."""
        scheduled_corpus_item_id = values.get("scheduledCorpusItemId")

        if scheduled_corpus_item_id and "tileId" not in values:
            values["tileId"] = cls._integer_hash(
                scheduled_corpus_item_id, MIN_TILE_ID, MAX_TILE_ID
            )

        return values

    @staticmethod
    def _integer_hash(s: str, start: int, stop: int) -> int:
        """:param s: String to be hashed.
        :param start: Minimum integer to be returned.
        :param stop: Integer that is greater than start. Maximum return value is stop - 1.
        :return: Integer hash of s in the range [start, stop)
        """
        return start + (int(hashlib.sha256(s.encode("utf-8")).hexdigest(), 16) % (stop - start))


class CuratedRecommendationsRequest(BaseModel):
    """Body schema for requesting a list of curated recommendations"""

    locale: Locale
    region: str | None = None
    count: int = 100
    topics: list[Topic | str] | None = None
    feeds: list[str] | None = None
    sections: list[SectionConfiguration] | None = None
    # Firefox sends the name and branch for Nimbus experiments on the "pocketNewtab" feature:
    # https://searchfox.org/mozilla-central/source/browser/components/newtab/lib/DiscoveryStreamFeed.sys.mjs
    # Allow any string value or null, because ExperimentName is not meant to be an exhaustive list.
    experimentName: ExperimentName | str | None = None
    experimentBranch: str | None = None
    enableInterestPicker: bool = False

    @field_validator("topics", mode="before")
    def validate_topics(cls, values):
        """Validate the topics param."""
        if values:
            if isinstance(values, list):
                valid_topics = []
                for value in values:
                    # if value is a valid Topic, add it to valid_topics
                    if isinstance(value, Topic):
                        valid_topics.append(value)
                    # if value is a string, check if its in enum Topic
                    # skip if invalid topic
                    elif isinstance(value, str):
                        try:
                            valid_topics.append(Topic(value))
                        except ValueError:
                            # Skip invalid topics
                            logger.warning(f"Invalid topic: {value}")
                            continue
                return valid_topics
            else:
                # Not wrapped in a list
                logger.warning(f"Topics not wrapped in a list: {values}")
        return []


class CuratedRecommendationsBucket(BaseModel):
    """A ranked list of curated recommendations"""

    recommendations: list[CuratedRecommendation]
    title: str | None = None


@unique
class TileSize(str, Enum):
    """Defines possible sizes for a tile in the layout."""

    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"


class Tile(BaseModel):
    """Defines properties for a single tile in a responsive layout."""

    size: TileSize
    position: int
    hasAd: bool
    hasExcerpt: bool

    @field_validator("hasExcerpt")
    def no_excerpt_on_small_tiles(cls, hasExcerpt, info: ValidationInfo):
        """Ensure small tiles do not have excerpts."""
        if info.data.get("size") == TileSize.SMALL and hasExcerpt:
            raise ValueError("Small tiles cannot have excerpts.")
        return hasExcerpt

    @field_validator("hasAd")
    def no_ad_on_small_or_large_tiles(cls, hasAd, info: ValidationInfo):
        """Ensure small and large tiles do not have ads."""
        if info.data.get("size") in {TileSize.SMALL, TileSize.LARGE} and hasAd:
            raise ValueError("Small or large tiles cannot have ads.")
        return hasAd


class ResponsiveLayout(BaseModel):
    """Defines layout properties for a specific column count."""

    columnCount: Annotated[int, Field(ge=1, le=4)]  # Restricts columnCount to integers from 1 to 4
    tiles: list[Tile]

    @field_validator("tiles")
    def validate_tile_positions(cls, tiles):
        """Ensure tile positions form a contiguous range from 0 to len(tiles) - 1, in any order."""
        if sorted(tile.position for tile in tiles) != list(range(len(tiles))):
            raise ValueError("ResponsiveLayout should not have a duplicate or missing position")
        return tiles


class Layout(BaseModel):
    """Defines a responsive layout configuration with multiple column layouts."""

    name: str
    responsiveLayouts: list[ResponsiveLayout]

    @field_validator("responsiveLayouts")
    def must_include_all_column_counts(cls, responsiveLayouts):
        """Ensure layouts include exactly one configuration for column counts 1 through 4."""
        if sorted(layout.columnCount for layout in responsiveLayouts) != [1, 2, 3, 4]:
            raise ValueError("Layout must have responsive layouts for 1, 2, 3, and 4 columns.")
        return responsiveLayouts


class Section(BaseModel):
    """A ranked list of curated recommendations with responsive layout configurations."""

    receivedFeedRank: int
    recommendations: list[CuratedRecommendation]
    title: str
    subtitle: str | None = None
    layout: Layout
    isFollowed: bool = False
    isBlocked: bool = False
    isInitiallyVisible: bool = True


class CuratedRecommendationsFeed(BaseModel):
    """Multiple lists of curated recommendations, that are currently in an experimental phase."""

    need_to_know: CuratedRecommendationsBucket | None = None
    fakespot: FakespotFeed | None = None

    # Sections
    # Renaming an alias of a section is a breaking change. New Tab stores section names when users
    # follow or block sections, and references 'top_stories_section' to show topic labels.
    top_stories_section: Section | None = None
    # Topic sections are named according to the lowercase Topic enum name, and aliased to the topic
    # id. The alias determines the section name in the JSON response.
    business: Section | None = Field(None, alias="business")
    career: Section | None = Field(None, alias="career")
    arts: Section | None = Field(None, alias="arts")
    food: Section | None = Field(None, alias="food")
    health_fitness: Section | None = Field(None, alias="health")
    home: Section | None = Field(None, alias="home")
    personal_finance: Section | None = Field(None, alias="finance")
    politics: Section | None = Field(None, alias="government")
    sports: Section | None = Field(None, alias="sports")
    technology: Section | None = Field(None, alias="tech")
    travel: Section | None = Field(None, alias="travel")
    education: Section | None = Field(None, alias="education")
    gaming: Section | None = Field(None, alias="hobbies")
    parenting: Section | None = Field(None, alias="society-parenting")
    science: Section | None = Field(None, alias="education-science")
    self_improvement: Section | None = Field(None, alias="society")

    def has_topic_section(self, topic: Topic) -> bool:
        """Check if a section for the given topic exists as an attribute."""
        return hasattr(self, topic.name.lower())

    def get_section_by_topic_id(self, serp_topic_id: str) -> Section | None:
        """Get a section for the given SERP topic ID."""
        for field_name, model_field in self.model_fields.items():
            if model_field.alias == serp_topic_id:
                return cast(Section, getattr(self, field_name, None))
        return None

    def get_sections(self) -> list[tuple[Section, str]]:
        """Get a list of all sections as tuples, where each tuple is a Section and its ID."""
        return [
            (feed, str(model_field.alias))  # alias defines the section id
            for field_name, model_field in self.model_fields.items()
            if (feed := getattr(self, field_name)) is not None and type(feed) is Section
        ]

    def set_topic_section(self, topic: Topic, section: Section):
        """Set a section for the given topic."""
        setattr(self, topic.name.lower(), section)


class InterestPickerSection(BaseModel):
    """Model representing a single section entry in the interest picker."""

    sectionId: str


class InterestPicker(BaseModel):
    """Model representing the interest picker component for following sections."""

    receivedFeedRank: int
    title: str
    subtitle: str
    sections: list[InterestPickerSection]


class CuratedRecommendationsResponse(BaseModel):
    """Response schema for a list of curated recommendations"""

    recommendedAt: int
    data: list[CuratedRecommendation]
    feeds: CuratedRecommendationsFeed | None = None
    interestPicker: InterestPicker | None = None
