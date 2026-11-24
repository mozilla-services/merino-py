"""Merino V1 API for New Tab curated recommendations"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from merino.curated_recommendations import get_legacy_provider
from merino.curated_recommendations import get_provider as get_corpus_api_provider
from merino.curated_recommendations.legacy.protocol import (
    CuratedRecommendationsLegacyFx114Request,
    CuratedRecommendationsLegacyFx114Response,
    CuratedRecommendationsLegacyFx115Fx129Request,
    CuratedRecommendationsLegacyFx115Fx129Response,
)
from merino.curated_recommendations.legacy.provider import LegacyCuratedRecommendationsProvider
from merino.curated_recommendations.protocol import (
    CuratedRecommendationsRequest,
    CuratedRecommendationsResponse,
)
from merino.curated_recommendations.provider import CuratedRecommendationsProvider

router = APIRouter()


@router.post("/curated-recommendations", summary="Curated recommendations for New Tab")
async def curated_content(
    curated_recommendations_request: CuratedRecommendationsRequest,
    provider: CuratedRecommendationsProvider = Depends(get_corpus_api_provider),
) -> CuratedRecommendationsResponse:
    """Query Merino for curated recommendations.

    This endpoint accepts POST requests and takes parameters as a JSON body.

    **JSON body:**

    - `locale`: The Firefox installed locale, for example en, en-US, de-DE.
        See the Request body schema below for the full list of supported values.
        This will determine the language of the recommendations.
    - `region`: [Optional] The country-level region, for example US or IE (Ireland).
        This will help return more relevant recommendations. If `region` is missing or cannot
        be parsed as a 2-letter code, it is derived from the second part of the `locale`
        parameter, if present (e.g. en-US -> US).
    - `count`: [Optional] The maximum number of recommendations in the legacy grid response
        (the `data` list). Defaults to 100. Ignored when the sections feed is requested.
    - `feeds`: [Optional] A list of feeds to include; "sections" is the only recognized value.
        When "sections" is requested, recommendations are grouped into topic sections in the
        `feeds` response field; otherwise a legacy grid response is returned in `data`.
    - `sections`: [Optional] The user's followed and blocked sections. Followed sections rank
        directly below the top stories section (`followedAt` orders them). Blocking removes
        recommendations whose topic matches the blocked section id; other blocked sections are
        only flagged `isBlocked`. Only affects responses with sections.
    - `enableInterestPicker`: [Optional] When true and sections are returned, sections get
        `isInitiallyVisible` set, and the response includes an interest picker (a prompt to
        follow more sections) if at least 8 followable sections are not initially visible.
    - `inferredInterests`: [Optional] A dictionary of interests with relative values, computed
        locally by the client; it must include a `model_id` to affect ranking. Personalizes the
        ranking of sections and items. When present, the response includes `inferredLocalModel`.
    - `coarseOs`: [Optional] Coarse operating system (mac, win, linux, android, ios, other).
        Reserved for future use; it currently does not affect the response.
    - `utcOffset`: [Optional] The user's UTC offset in hours (0-23). Reserved for future use;
        it currently does not affect the response.
    - `experimentName`: [Optional] The Nimbus New Tab experiment name that the user is enrolled in.
        When an experiment _only_ requires backend changes, this allows us to run the experiments
        without waiting on the Firefox release cycle. When an experiment _does_ require changes in
        Firefox, other parameters can be changed, such as we did for topic preferences. The API
        schema does not list all New Tab experiments; only those which the backend uses to change
        its behavior. Any string or null is accepted.
    - `experimentBranch`: [Optional] The branch name of the Nimbus experiment that the user is in.

    Unknown body parameters are accepted and ignored, including the retired `topics` parameter.
    """
    return await provider.fetch(curated_recommendations_request)


@router.get(
    "/curated-recommendations/legacy-115-129",
    summary="Curated Recommendations for New Tab Firefox v115-129",
)
async def curated_content_legacy_fx_115_129(
    query_params: Annotated[CuratedRecommendationsLegacyFx115Fx129Request, Query()],
    curated_corpus_provider: CuratedRecommendationsProvider = Depends(get_corpus_api_provider),
    legacy_provider: LegacyCuratedRecommendationsProvider = Depends(get_legacy_provider),
) -> CuratedRecommendationsLegacyFx115Fx129Response:
    """Query for a list of curated content recommendations for legacy Firefox desktop clients
    (versions 115–129) using the legacy schema structure.

    This endpoint maps modern recommendation data into a response format compatible with
    older Firefox versions that expect the original `/desktop/v1/recommendations` structure.

    Query parameters:
    - `locale`: The Firefox installed locale, for example en, en-US, de-DE.
        See the Request body schema below for the full list of supported values.
        This will determine the language of the recommendations.
    - `region`: [Optional] The country-level region, for example US or IE (Ireland).
        This will help return more relevant recommendations. If `region` is not provided,
        then region is extracted from the `locale` parameter if it contains two parts (e.g. en-US).
    - `count`: [Optional] The maximum number of recommendations to return. Defaults to 30.
    """
    return await legacy_provider.fetch_recommendations_for_legacy_fx_115_129(
        query_params, curated_corpus_provider
    )


@router.get(
    "/curated-recommendations/legacy-114",
    summary="Legacy Recommendations for New Tab Fx <= 114",
)
async def curated_content_legacy_fx_114(
    query_params: Annotated[CuratedRecommendationsLegacyFx114Request, Query()],
    curated_corpus_provider: CuratedRecommendationsProvider = Depends(get_corpus_api_provider),
    legacy_provider: LegacyCuratedRecommendationsProvider = Depends(get_legacy_provider),
) -> CuratedRecommendationsLegacyFx114Response:
    """Query for a list of curated content recommendations for legacy Firefox desktop clients
    (versions <= 114) using the legacy schema structure.

    This endpoint maps modern recommendation data into a response format compatible with
    older Firefox versions that expect the original `/v3/firefox/global-recs` structure.

    Query parameters:
    - `locale_lang`: The Firefox installed locale, for example en, en-US, de-DE.
        See the Request body schema below for the full list of supported values.
        This will determine the language of the recommendations.
    - `region`: [Optional] The country-level region, for example US or IE (Ireland).
        This will help return more relevant recommendations. If `region` is not provided,
        then region is extracted from the `locale` parameter if it contains two parts (e.g. en-US).
    - `count`: [Optional] The maximum number of recommendations to return. Defaults to 10.
    """
    return await legacy_provider.fetch_recommendations_for_legacy_fx_114(
        query_params, curated_corpus_provider
    )
