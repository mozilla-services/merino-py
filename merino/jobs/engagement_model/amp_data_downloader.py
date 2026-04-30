"""Download engagement metrics for AMP from BigQuery table"""

import logging
from typing import Any

from google.cloud.bigquery import Client
from google.api_core.exceptions import GoogleAPIError

logger = logging.getLogger(__name__)


class EngagementDataDownloader:
    """Download engagement data for AMP"""

    KEYWORD_QUERY_HISTORICAL = """
SELECT
 LOWER(advertiser) AS advertiser,
 LOWER(query) AS query,
 COUNTIF(is_clicked) AS clicks,
 COUNT(*) AS impressions
FROM `moz-fx-data-shared-prod.search_terms_derived.suggest_impression_sanitized_v3`
WHERE
 submission_timestamp BETWEEN TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 9 DAY) AND TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 2 DAY)
AND query is not NULL
GROUP BY 1, 2
HAVING impressions > 500
ORDER BY 1, 4 DESC
"""

    KEYWORD_QUERY_LIVE = """
SELECT
 LOWER(advertiser) AS advertiser,
 LOWER(query) AS query,
 COUNTIF(is_clicked) AS clicks,
 COUNT(*) AS impressions
FROM `moz-fx-data-shared-prod.search_terms_derived.suggest_impression_sanitized_v3`
WHERE
 submission_timestamp BETWEEN TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 48 HOUR) AND CURRENT_TIMESTAMP()
AND query is not NULL
GROUP BY 1, 2
HAVING impressions > 200
ORDER BY 1, 4 DESC
"""

    client: Client

    def __init__(self, source_gcp_project: str) -> None:
        self.client = Client(source_gcp_project)

    def _fetch_rows(self, query: str, label: str) -> list[dict[str, Any]]:
        """Execute a BigQuery query and return parsed rows.

        Args:
            query: The SQL query to execute.
            label: A short label (e.g. "historical", "live") used in log messages.

        Returns:
            list[dict[str, Any]]: A list of engagement records containing
            advertiser, query, impressions, and clicks.

        Raises:
            RuntimeError: If the BigQuery query fails.
        """
        try:
            query_job = self.client.query(query)
            results = query_job.result()
        except GoogleAPIError as e:
            logger.error(
                "BigQuery query failed while downloading %s AMP engagement data",
                label,
                exc_info=True,
            )
            raise RuntimeError(f"Failed to fetch {label} AMP engagement data from BigQuery") from e

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
                logger.warning("Unexpected row format in BigQuery results (%s): %s", label, row)
                continue

        if not engagement_data:
            logger.warning("%s AMP engagement query returned no rows", label)

        return engagement_data

    def download_historical_data(self) -> list[dict[str, Any]]:
        """Execute the historical AMP engagement query."""
        return self._fetch_rows(self.KEYWORD_QUERY_HISTORICAL, "historical")

    def download_live_data(self) -> list[dict[str, Any]]:
        """Execute the live AMP engagement query."""
        return self._fetch_rows(self.KEYWORD_QUERY_LIVE, "live")

    @staticmethod
    def transform_data(
        historical: list[dict[str, Any]],
        live: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Merge historical and live keyword-level AMP data into an advertiser/query-keyed dict.

        Both datasets are optional per advertiser/query pair — a key may have only
        historical, only live, or both.
        """
        result: dict[str, Any] = {}

        for row in historical:
            key = f"{row['advertiser']}/{row['query']}"
            if key not in result:
                result[key] = {}
            result[key]["historical"] = {
                "impressions": row["impressions"],
                "clicks": row["clicks"],
            }

        for row in live:
            key = f"{row['advertiser']}/{row['query']}"
            if key not in result:
                result[key] = {}
            result[key]["live"] = {
                "impressions": row["impressions"],
                "clicks": row["clicks"],
            }

        return result

    @staticmethod
    def aggregate_data(_transformed: dict[str, Any]) -> dict[str, int]:
        """Aggregate impressions and clicks from keyword-level AMP data."""
        # Not currently consumed — returning zeros until a use case is defined.
        return {"impressions": 0, "clicks": 0}
