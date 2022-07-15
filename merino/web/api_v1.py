import asyncio
import uuid
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from merino.providers import default_providers
from merino.providers import providers as active_providers


class Provider(BaseModel):
    """
    Model for the providers response.
    """

    id: str
    availability: str


router = APIRouter()


SUGGEST_RESPONSE = {
    "suggestions": [],
    "client_variants": [],
    "server_variants": [],
    "request_id": "",
}


@router.get("/suggest", tags=["suggest"], summary="Merino suggest endpoint")
async def suggest(q: str, providers: str | None = None) -> Any:
    """
    Query Merino for suggestions.

    Args:
    - `q`: The query string
    - `providers`: [Optional] A comma separated string indicating the suggestion providers for
      this query

    Returns:
    A list of suggestions or an empty list if nothing was found.
    """
    if providers is not None:
        search_from = [
            active_providers[p] for p in providers.split(",") if p in active_providers
        ]
    else:
        search_from = default_providers
    lookups = [p.query(q) for p in search_from]
    results = await asyncio.gather(*lookups)
    if len(results):
        SUGGEST_RESPONSE["suggestions"] = [
            sugg for provider_results in results for sugg in provider_results
        ]
    SUGGEST_RESPONSE["request_id"] = str(uuid.uuid4())
    return SUGGEST_RESPONSE


@router.get(
    "/providers",
    tags=["providers"],
    summary="Merino provider endpoint",
    response_model=list[Provider],
)
async def providers() -> Any:
    """
    Query Merino for suggestion providers.

    Returns:
    A list of search providers.
    """
    return [
        {"id": id, "availability": provider.availability()}
        for id, provider in active_providers.items()
    ]
