"""Download engagement metrics for Wikipedia from Biq Query table"""

from google.cloud.bigquery import Client


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
        """Download engagement data from BigQuery and return formatted JSON objects"""
        query_job = self.client.query(self.QUERY)
        row = next(query_job.result(), None)
        if row is None:
            return {"impressions": 0, "clicks": 0}
        return {
            "impressions": int(row["impressions"]),
            "clicks": int(row["clicks"]),
        }
