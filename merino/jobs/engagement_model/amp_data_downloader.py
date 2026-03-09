"""Download engagement metrics for AMP from Biq Query table"""

from typing import Any

from google.cloud.bigquery import Client


class EngagementDataDownloader:
    """Download engagement data for AMP"""

    QUERY = """
SELECT
  metrics.string.quick_suggest_advertiser AS advertiser,
  metrics.string.quick_suggest_block_id AS suggestion_id,
  metrics.string.quick_suggest_match_type AS match_type,
  COUNT(*) AS impressions,
  COUNTIF(metrics.boolean.quick_suggest_is_clicked) AS clicks
FROM `moz-fx-data-shared-prod.firefox_desktop_live.quick_suggest_v1`
WHERE submission_timestamp BETWEEN TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 DAY) AND CURRENT_TIMESTAMP()
AND client_info.app_channel = "release"
AND metrics.boolean.quick_suggest_improve_suggest_experience
AND metrics.string.quick_suggest_request_id IS NOT NULL
AND metrics.string.quick_suggest_ping_type = "quicksuggest-impression"
GROUP BY 1, 2, 3
ORDER BY 1, 5 DESC, 4 DESC
"""
    client: Client

    def __init__(self, source_gcp_project: str) -> None:
        self.client = Client(source_gcp_project)

    def download_data(self) -> list[dict[str, Any]]:
        """Download engagement data from BigQuery and return formatted JSON objects"""

        query_job = self.client.query(self.QUERY)
        results = query_job.result()

        return [
            {
                "suggestion_id": row["suggestion_id"],
                "impressions": row["impressions"],
                "clicks": row["clicks"],
                "advertiser": row["advertiser"],
                "match_type": row["match_type"],
            }
            for row in results
        ]
