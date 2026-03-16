"""Download engagement metrics for Wikipedia from BigQuery table"""

import logging

from google.api_core.exceptions import GoogleAPIError
from google.cloud.bigquery import Client

logger = logging.getLogger(__name__)


class EngagementDataDownloader:
    """Download engagement data for Wikipedia"""

    QUERY = """
SELECT
  COUNT(*) AS impressions,
  COUNTIF(
      product_selected_result = res.product_result_type
      AND event_action = 'engaged'
  ) AS clicks
FROM `moz-fx-data-shared-prod.firefox_desktop.urlbar_events`
CROSS JOIN UNNEST(results) AS res
WHERE submission_date BETWEEN DATE_SUB(CURRENT_DATE(), INTERVAL 1 DAY) AND CURRENT_DATE()
AND res.product_result_type = "wikipedia_dynamic"
AND is_terminal
AND normalized_channel = "release"
"""
    client: Client

    def __init__(self, source_gcp_project: str) -> None:
        self.client = Client(source_gcp_project)

    def download_data(self) -> dict[str, int]:
        """Execute the Wikipedia engagement query and return aggregated metrics.

        Returns:
            dict[str, int]: A dictionary containing total impressions and clicks.

        Raises:
            RuntimeError: If the BigQuery query fails.
        """
        try:
            query_job = self.client.query(self.QUERY)
            row = next(query_job.result(), None)
        except GoogleAPIError as e:
            logger.error(
                "BigQuery query failed while downloading Wikipedia engagement data",
                exc_info=True,
            )
            raise RuntimeError("Failed to fetch Wikipedia engagement data from BigQuery") from e

        if row is None:
            logger.warning("Wikipedia engagement query returned no rows")
            return {"impressions": 0, "clicks": 0}

        try:
            return {
                "impressions": int(row["impressions"]),
                "clicks": int(row["clicks"]),
            }
        except KeyError as e:
            logger.error("Unexpected row format in Wikipedia engagement results: %s", row)
            raise RuntimeError("Wikipedia engagement data was missing expected fields") from e
