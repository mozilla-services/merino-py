"""A utility module for merino API query params."""

import functools
import logging
from typing import Optional

from fastapi import HTTPException, Request

from merino.middleware import ScopeKey
from merino.middleware.geolocation import Location

logger = logging.getLogger(__name__)


@functools.lru_cache(maxsize=1000)
def get_accepted_languages(languages: str | None) -> list[str]:
    """Retrieve filtered list of languages that merino accepts."""
    if languages:
        try:
            if languages == "*":
                return ["en-US"]
            result = []
            for lang in languages.split(","):
                parts = lang.strip().split(";q=")
                language = parts[0]
                quality = float(parts[1]) if len(parts) > 1 else 1.0  # Default q-value is 1.0
                result.append((language, quality))

            # Sort by quality in descending order
            result.sort(key=lambda x: x[1], reverse=True)
            return [language[0] for language in result]
        except Exception:
            return ["en-US"]
    return ["en-US"]


def validate_suggest_custom_location_params(
    city: Optional[str],
    region: Optional[str],
    regions: Optional[str],
    country: Optional[str],
) -> None:
    """Validate that triplet of either city, region, country
    or city, regions, country have all non None values if one is a non None value.
    """
    if any([city, region, country, regions]):
        if not all([city, region, country]) and not all([city, regions, country]):
            logger.warning(
                "HTTP 400: Invalid query parameters: one of the following triplet params require all non None values: "
                "[`city`, `region`, `country`] or [`city`,`regions`, `country`]."
            )
            raise HTTPException(
                status_code=400,
                detail="Invalid query parameters: one of the following triplet params require all non None values: "
                "[`city`, `region`, `country`] or [`city`,`regions`, `country`].",
            )
        if regions and region:
            logger.warning(
                "HTTP 400: Invalid query parameters: either `region` or `regions` can be present."
            )
            raise HTTPException(
                status_code=400,
                detail="Invalid query parameters: either `region` or `regions` can be present.",
            )


def refine_geolocation_for_suggestion(
    request: Request,
    city: Optional[str],
    region: Optional[str],
    regions: Optional[str],
    country: Optional[str],
) -> Location:
    """Generate a refined geolocation object based on optional city, region, and country parameters
    for the suggest endpoint. If all parameters are provided, the geolocation data is updated
    with the specified city, region, and country. Otherwise, the original geolocation data is used.

    Args:
        request (Request): The request containing geolocation data in the scope.
        city (Optional[str]): The name of the city to include in the geolocation, if available.
        region (Optional[str]): The name of the region to include in the geolocation, if available.
        regions (Optional[str]): The name of possible regions to include in the geolocation, if available.
        country (Optional[str]): The name of the country to include in the geolocation, if available.

    Returns:
        Location: A Location object with refined geolocation data based on provided parameters.
    """
    geolocation: Location = request.scope[ScopeKey.GEOLOCATION].model_copy()
    regions_list = regions.split(",") if regions else [region] if region else []

    if country and regions_list and city:
        geolocation = geolocation.model_copy(
            update={
                "city": city,
                "regions": regions_list,
                "country": country,
            }
        )
    return geolocation
