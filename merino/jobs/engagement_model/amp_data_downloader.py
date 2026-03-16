"""Download engagement metrics for AMP from BigQuery table"""

import logging
from typing import Any

from google.cloud.bigquery import Client
from google.api_core.exceptions import GoogleAPIError

logger = logging.getLogger(__name__)


class EngagementDataDownloader:
    """Download engagement data for AMP"""

    QUERY = """
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

    client: Client

    def __init__(self, source_gcp_project: str) -> None:
        self.client = Client(source_gcp_project)

    def download_data(self) -> list[dict[str, Any]]:
        """Execute the AMP engagement query and return aggregated engagement data.

        Returns:
            list[dict[str, Any]]: A list of engagement records containing
            advertiser, impressions, and clicks.

        Raises:
            RuntimeError: If the BigQuery query fails.
        """
        try:
            query_job = self.client.query(self.QUERY)
            results = query_job.result()

        except GoogleAPIError as e:
            logger.error(
                "BigQuery query failed while downloading AMP engagement data",
                exc_info=True,
            )
            raise RuntimeError("Failed to fetch AMP engagement data from BigQuery") from e

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
            logger.warning("AMP engagement query returned no rows")

        return engagement_data
