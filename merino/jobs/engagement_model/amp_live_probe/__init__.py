"""Probe job to verify Airflow has access to the live AMP keyword engagement dataset."""

import logging
import sys

import typer
from google.api_core.exceptions import GoogleAPIError
from google.cloud.bigquery import Client, QueryJobConfig

from merino.configs import settings

logger = logging.getLogger(__name__)

QUERY = """
WITH base AS (
 SELECT
   LOWER(a.jsonPayload.fields.query) as query,
   LOWER(b.metrics.string.quick_suggest_advertiser) as advertiser,
   b.metrics.boolean.quick_suggest_is_clicked as is_clicked
 FROM `suggest-searches-prod-a30f.logs.stdout` a
 JOIN `moz-fx-data-shared-prod.firefox_desktop_live.quick_suggest_v1` b
 ON a.jsonPayload.fields.rid = b.metrics.string.quick_suggest_request_id
 WHERE a.timestamp BETWEEN TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 DAY) AND CURRENT_TIMESTAMP()
 AND b.submission_timestamp BETWEEN TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 DAY) AND CURRENT_TIMESTAMP()
)
SELECT
 advertiser,
 query,
 COUNT(*) as impressions,
 COUNTIF(is_clicked) as clicks
FROM base
GROUP BY 1, 2
HAVING impressions > 200
ORDER BY 3 DESC
"""

cli = typer.Typer(
    name="probe_amp_live_access",
    help="Probe BigQuery access to the live AMP keyword engagement dataset",
)


@cli.command()
def probe_amp_live_access() -> None:  # pragma: no cover
    """Dry-run the live AMP keyword query to verify dataset access without executing it."""
    logger.info("Probing access to live AMP keyword engagement dataset...")

    try:
        client = Client(settings.engagement.gcs_bq_project)
        job_config = QueryJobConfig(dry_run=True, use_query_cache=False)
        job = client.query(QUERY, job_config=job_config)
        logger.info(
            "Access confirmed. Estimated bytes to be processed: %d",
            job.total_bytes_processed,
        )
    except GoogleAPIError as e:
        logger.error("Access check failed: %s", str(e))
        sys.exit(1)
