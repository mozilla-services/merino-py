"""Upday specific data provider for the New Tab."""
import logging
from typing import Any, Tuple

from httpx import AsyncClient, BasicAuth, HTTPError

from merino.newtab.base import Recommendation

# The path to the Authentication Endpoint of the Upday API
AUTH_URL_PATH = "/v1/oauth/token"
LOCAL_ARTICLES_URL_PATH = "/v1/ntk/articles"

logger = logging.getLogger(__name__)


class UpdayError(Exception):
    """Errors related to calling the Upday API."""

    pass


class UpdayProvider:
    """Provider for getting Upday Information."""

    def __init__(self, username: str, password: str, http_client: AsyncClient):
        """Initialize the Upday Provider to get information."""
        self.basic_auth = BasicAuth(username=username, password=password)
        self.http_client = http_client

    async def get_upday_recommendations(
        self, locale: str, language: str
    ) -> list[Recommendation]:
        """Get the Upday recommendations given the local and language of the request."""
        access_token, token_type = await self._get_access_token()

        articles = await self._get_articles_from_upday(
            access_token, language, locale, token_type
        )

        recommendations = []
        for article in articles:
            url_to_use: str = (
                article["partnerUrl"]
                if article.get("partnerUrl")
                else article.get("url")
            )
            recommendations.append(
                Recommendation(
                    url=url_to_use,
                    title=article["title"],
                    excerpt=article["previewText"],
                    publisher=article["source"],
                    image_url=article["imageUrl"],
                )
            )
        return recommendations

    async def _get_articles_from_upday(
        self, access_token: str, language: str, locale: str, token_type: str
    ) -> list[dict[str, Any]]:
        """Help get articles from Upday."""
        headers = {"Authorization": f"{token_type} {access_token}"}
        try:
            response = await self.http_client.get(
                LOCAL_ARTICLES_URL_PATH,
                headers=headers,
                params={"country": locale, "language": language},
            )
            response.raise_for_status()
        except HTTPError as error:
            raise UpdayError("Could not get articles from Upday.") from error
        articles: list[dict[str, Any]] = response.json()["articles"]
        return articles

    async def _get_access_token(self) -> Tuple[str, str]:
        """Help get the access token required to use to get articles from Upday."""
        try:
            response = await self.http_client.post(
                AUTH_URL_PATH,
                auth=self.basic_auth,
                params={"grant_type": "client_credentials"},
            )
            response.raise_for_status()
        except HTTPError as error:
            raise UpdayError(
                "Could not get authentication token from Upday."
            ) from error
        response_json = response.json()
        access_token = response_json.get("access_token")
        token_type = response_json.get("token_type")
        return access_token, token_type

    async def shutdown(self) -> None:
        """Close out connection resources."""
        await self.http_client.aclose()
