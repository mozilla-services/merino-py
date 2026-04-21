"""Download engagement metrics for AMP from BigQuery table"""

import logging
from typing import Any

from google.cloud.bigquery import Client
from google.api_core.exceptions import GoogleAPIError

logger = logging.getLogger(__name__)


class EngagementDataDownloader:
    """Download engagement data for AMP"""

    ADVERTISER_QUERY = """
SELECT
  metrics.string.quick_suggest_advertiser AS advertiser,
  COUNT(*) AS impressions,
  COUNTIF(metrics.boolean.quick_suggest_is_clicked) AS clicks
FROM `moz-fx-data-shared-prod.firefox_desktop_live.quick_suggest_v1`
WHERE submission_timestamp BETWEEN TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 DAY) AND CURRENT_TIMESTAMP()
AND client_info.app_channel = "release"
AND metrics.boolean.quick_suggest_improve_suggest_experience
AND metrics.string.quick_suggest_request_id IS NOT NULL
AND metrics.string.quick_suggest_ping_type = "quicksuggest-impression"
GROUP BY 1
ORDER BY 1, 3 DESC, 2 DESC
"""

    KEYWORD_QUERY = """
SELECT
 LOWER(advertiser),
 LOWER(query),
 COUNTIF(is_clicked) AS clicks,
 COUNT(*) AS impressions
FROM `moz-fx-data-shared-prod.search_terms_derived.suggest_impression_sanitized_v3`
WHERE
 submission_timestamp BETWEEN TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY) AND CURRENT_TIMESTAMP()
AND query is not NULL
GROUP BY 1, 2
HAVING impressions > 500
ORDER BY 1, 4 DESC
"""

    client: Client

    def __init__(self, source_gcp_project: str) -> None:
        self.client = Client(source_gcp_project)

    def download_by_advertiser(self) -> list[dict[str, Any]]:
        """Execute the advertiser-level AMP engagement query.

        Returns:
            list[dict[str, Any]]: A list of engagement records containing
            advertiser, impressions, and clicks.

        Raises:
            RuntimeError: If the BigQuery query fails.
        """
        try:
            query_job = self.client.query(self.ADVERTISER_QUERY)
            results = query_job.result()

        except GoogleAPIError as e:
            logger.error(
                "BigQuery query failed while downloading advertiser-level AMP engagement data",
                exc_info=True,
            )
            raise RuntimeError(
                "Failed to fetch advertiser-level AMP engagement data from BigQuery"
            ) from e

        engagement_data: list[dict[str, Any]] = []

        for row in results:
            try:
                engagement_data.append(
                    {
                        "advertiser": row["advertiser"],
                        "impressions": int(row["impressions"]),
                        "clicks": int(row["clicks"]),
                    }
                )
            except KeyError:
                logger.warning("Unexpected row format in BigQuery results: %s", row)
                continue

        if not engagement_data:
            logger.warning("Advertiser-level AMP engagement query returned no rows")

        return engagement_data

    def download_by_keyword(self) -> list[dict[str, Any]]:
        """Execute the keyword-level AMP engagement query.

        Returns:
            list[dict[str, Any]]: A list of engagement records containing
            advertiser, query, impressions, and clicks.

        Raises:
            RuntimeError: If the BigQuery query fails.
        """
        try:
            query_job = self.client.query(self.KEYWORD_QUERY)
            results = query_job.result()

        except GoogleAPIError as e:
            logger.error(
                "BigQuery query failed while downloading keyword-level AMP engagement data",
                exc_info=True,
            )
            raise RuntimeError(
                "Failed to fetch keyword-level AMP engagement data from BigQuery"
            ) from e

        engagement_data: list[dict[str, Any]] = []

        for row in results:
            try:
                engagement_data.append(
                    {
                        "advertiser": row["advertiser"],
                        "query": row["query"],
                        "impressions": int(row["impressions"]),
                        "clicks": int(row["clicks"]),
                    }
                )
            except KeyError:
                logger.warning("Unexpected row format in BigQuery results: %s", row)
                continue

        if not engagement_data:
            logger.warning("Keyword-level AMP engagement query returned no rows")

        return engagement_data

    @staticmethod
    def transform_by_advertiser(data: list[dict[str, Any]]) -> dict[str, Any]:
        """Transform advertiser-level AMP data into an advertiser-keyed dict."""
        return {row["advertiser"]: row for row in data}

    @staticmethod
    def aggregate_by_advertiser(data: list[dict[str, Any]]) -> dict[str, int]:
        """Aggregate impressions and clicks across all advertiser-level AMP rows."""
        return {
            "impressions": sum(int(row["impressions"]) for row in data),
            "clicks": sum(int(row["clicks"]) for row in data),
        }

    @staticmethod
    def transform_by_keyword(data: list[dict[str, Any]]) -> dict[str, Any]:
        """Transform keyword-level AMP data into an advertiser/query-keyed dict with historical metrics."""
        return {
            f"{row['advertiser']}/{row['query']}": {
                "historical": {
                    "impressions": row["impressions"],
                    "clicks": row["clicks"],
                }
            }
            for row in data
        }

    @staticmethod
    def aggregate_by_keyword(transformed: dict[str, Any]) -> dict[str, int]:
        """Aggregate impressions and clicks from keyword-level transformed AMP data."""
        return {
            "impressions": sum(int(v["historical"]["impressions"]) for v in transformed.values()),
            "clicks": sum(int(v["historical"]["clicks"]) for v in transformed.values()),
        }
