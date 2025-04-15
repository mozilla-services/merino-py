"""Abstract class for Providers"""

from abc import ABC, abstractmethod
from enum import Enum

from pydantic import BaseModel, Field, HttpUrl

from merino.configs import settings
from merino.middleware.geolocation import Location
from merino.providers.suggest.custom_details import CustomDetails


class SuggestionRequest(BaseModel):
    """A request for suggestions."""

    query: str
    geolocation: Location
    languages: list[str] | None = None
    request_type: str | None = None
    city: str | None = None
    region: str | None = None
    country: str | None = None


class Category(Enum):
    """Enum of possible interests for a suggestion."""

    Inconclusive = 0
    Animals = 1
    Arts = 2
    Autos = 3
    Business = 4
    Career = 5
    Education = 6
    Fashion = 7
    Finance = 8
    Food = 9
    Government = 10
    # Disable this per policy consultation
    # Health = 11
    Hobbies = 12
    Home = 13
    News = 14
    RealEstate = 15
    Society = 16
    Sports = 17
    Tech = 18
    Travel = 19


class BaseSuggestion(BaseModel):
    """Base model for suggestions.

    **Deprecation Notice:**
    The original usage of this model was to extend it for specific providers.
    These extended suggestions added extra fields to the top level of `BaseSuggestion`.
    For completeness (as the autogenerated documentation cannot access these models)
    we will reference the extra fields that the Suggestion object may also include
    in this documentation.
    For adding new Providers with custom suggestion fields, we should be adding to the
    `CustomDetails` object.
    For more context and list of providers affected, please consult
    [this ADR](https://mozilla-services.github.io/merino-py/adr/0002-merino-general-response.html).

    Extra Provider Specific Fields:
    -------------------------------

    - `block_id` - A number that can be used, along with the `provider` field below,
      to uniquely identify this suggestion. Two suggestions with the same `provider`
      and `block_id` should be treated as the same suggestion, even if other fields,
      such as `click_url` change. Merino will enforce that they are equivalent from
      a user's point of view.
    - `full_keyword` - In the case that the query was a partial match to the
      suggestion, this is the completed query that would also match this query. For
      example, if the user was searching for fruit and typed "appl", this field
      might contain the string "apples". This is suitable to show as a completion of
      the user's input. This field should be treated as plain text.
    - `impression_url` - A provider specified telemetry URL that should be notified
      if the browser shows this suggestion to the user. This is used along with
      `click_url` to monitor the relevancy of suggestions. This field may be null, in
      which case no impression ping is required for this suggestion provider.
    - `click_url` - A provider specified telemetry URL that should be notified if
      the user selects this suggestion. This should only be notified as the result
      of positive user action, and only if the user has navigated to the page
      specified in the `url` field. This field may be null, in
      which case no click ping is required for this suggestion provider.
    - `advertiser` - The name of the advertiser, such as "Nike". Note that a `provider`
      could have multiple `advertiser`s.
    - `is_sponsored` - A boolean indicating if this suggestion is sponsored content.
      If this is true, the UI must indicate to the user that the suggestion is
      sponsored.
    - `is_top_pick` - A boolean indicating if the suggestion requires a "top pick"
      UI treatment.
    - `city_name` - A string representing the city name. To be used with weather suggestions.
    - `current_conditions` - An object that contains the current weather conditions for a location.
      To be used with weather suggestions. Please reference `CurrentCondition` model
      for more information.
    - `forecast` - An object that contains the one-day weather forecast information.
      To be used with weather suggestions. Please reference `Forecast` model for more information.
    """

    title: str = Field(
        description="The full title of the suggestion resulting from the query. "
        "Using the example of apples above, 'this might be \"Types of Apples "
        'in the Pacific Northwest". This field should be treated as plain text.'
    )
    url: HttpUrl = Field(
        description=" The URL of the page that should be navigated to if the user "
        "selects this suggestion. This will be a resource with the title specified in the "
        "`title` field."
    )
    provider: str = Field(
        description="A string that identifies the provider of this suggestion, such as "
        '"adM". In general, this field is not intended to be directly displayed to the user.'
    )
    is_sponsored: bool = Field(
        description="A boolean indicating if this suggestion is sponsored content. "
        "If this is true, the UI must indicate to the user that the suggestion is sponsored."
    )
    score: float = Field(
        description="A value between 0.0 and 1.0 used to compare suggestions. "
        "When choosing a suggestion to show the user, higher scored suggestions are preferred."
    )
    description: str | None = Field(
        default=None, description="[Optional] Text description of the suggestion."
    )
    icon: str | None = Field(
        default=None,
        description="[Optional] A URL of an image to display alongside the suggestion."
        "This will be a small square image, suitable to be included inline with the text, "
        "such as a site's favicon.",
    )
    custom_details: CustomDetails | None = Field(
        default=None,
        description="[Optional] Object that contains provider specific fields.`custom_details` "
        "is keyed by the provider name and references custom schemas.",
    )
    categories: list[Category] | None = Field(
        default=None,
        description="[Optional] List that contains categories associated to the suggestion.",
    )


class BaseProvider(ABC):
    """Abstract class for suggestion providers."""

    _name: str
    _enabled_by_default: bool
    _query_timeout_sec: float = settings.runtime.query_timeout_sec

    @abstractmethod
    async def initialize(self) -> None:  # pragma: no cover
        """Abstract method for defining an initialize method for bootstrapping the Provider.
        This allows us to use Async API's within as well as initialize providers in parallel

        """
        ...

    async def shutdown(self) -> None:  # pragma: no cover
        """Shut down the Provider. The default implementaion is no-op."""
        return

    @abstractmethod
    async def query(self, srequest: SuggestionRequest) -> list[BaseSuggestion]:  # pragma: no cover
        """Query against this provider.

        Args:
          - `srequest`: the suggestion request.
        """
        ...

    def validate(self, srequest: SuggestionRequest) -> None:  # pragma: no cover
        """Validate the request. Raise an `HTTPException` for any validation errors.

        Args:
          - `srequest`: the suggestion request.
        Raise:
          - `HTTPException` for any validation errors.
        """
        return

    def normalize_query(self, query: str) -> str:  # pragma: no cover
        """Normalize the query string when passed to the provider.
        Each provider can extend this class given its requirements. Can be used to
        strip whitespace, handle case sensitivity, etc. Default is to return query unchanged.

        Trailing spaces are not stripped in Firefox, so stripping trailing spaces
        is advised. Each provider will have its specific use cases, and others
        will not require any logic for query normalization.
        """
        return query

    @property
    def enabled_by_default(self) -> bool:
        """Boolean indicating whether or not provider is enabled."""
        return self._enabled_by_default

    def hidden(self) -> bool:
        """Boolean indicating whether or not this provider is hidden."""
        return False

    def availability(self) -> str:
        """Return the status of this provider."""
        if self.hidden():
            return "hidden"
        elif self.enabled_by_default:
            return "enabled_by_default"
        else:
            return "disabled_by_default"

    @property
    def name(self) -> str:
        """Return the name of the provider for use in logging and metrics"""
        return self._name

    @property
    def query_timeout_sec(self) -> float:
        """Return the query timeout for this provider."""
        return self._query_timeout_sec
