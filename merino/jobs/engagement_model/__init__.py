"""CLI command to fetch engagement data."""

import json
import logging
from datetime import datetime
from typing import Any

import typer

from merino.jobs.engagement_model.amp_data_downloader import (
    EngagementDataDownloader as AMPDownloader,
)
from merino.configs import settings
from merino.jobs.engagement_model.wikipedia_data_downloader import (
    EngagementDataDownloader as WikiDownloader,
)
from merino.utils.gcs.gcs_uploader import GcsUploader

logger = logging.getLogger(__name__)

cli = typer.Typer(
    name="upload_engagement_data",
    help="Commands to fetch and upload user engagement data to GCS",
)


@cli.command()
def upload_engagement_data() -> None:  # pragma: no cover
    """Fetch AMP + Wikipedia engagement data and upload a JSON payload to GCS."""
    logger.info("Starting engagement data pipeline...")

    try:
        gcs_bq_project = settings.engagement.gcs_bq_project
        gcs_storage_bucket = settings.engagement.gcs_storage_bucket
        gcs_storage_project = settings.engagement.gcs_storage_project

        amp_data_downloader = AMPDownloader(gcs_bq_project)
        wiki_data_downloader = WikiDownloader(gcs_bq_project)

        amp_keyword_historical: list[dict[str, Any]] = (
            amp_data_downloader.download_historical_data_by_keyword()
        )
        amp_keyword_live: list[dict[str, Any]] = (
            amp_data_downloader.download_live_data_by_keyword()
        )
        wiki_data: dict[str, int] = wiki_data_downloader.download_data()

        transformed_amp_by_keyword = amp_data_downloader.transform_by_keyword(
            historical=amp_keyword_historical,
            live=amp_keyword_live,
        )

        amp_aggregated_by_keyword = amp_data_downloader.aggregate_by_keyword(
            transformed_amp_by_keyword
        )

        keyword_payload = {
            "amp": transformed_amp_by_keyword,
            "wiki_aggregated": {
                "impressions": int(wiki_data["impressions"]),
                "clicks": int(wiki_data["clicks"]),
            },
            "amp_aggregated": amp_aggregated_by_keyword,
        }

        keyword_content = json.dumps(keyword_payload, indent=2)

        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        destination_name_keyword = f"suggest-merino-exports/engagement/keyword/{timestamp}.json"
        latest_name_keyword = "suggest-merino-exports/engagement/keyword/latest.json"

        uploader = GcsUploader(
            destination_gcp_project=gcs_storage_project,
            destination_bucket_name=gcs_storage_bucket,
            destination_cdn_hostname="",
        )

        uploader.upload_content(
            content=keyword_content,
            destination_name=destination_name_keyword,
            content_type="application/json",
            forced_upload=True,
        )

        uploader.upload_content(
            content=keyword_content,
            destination_name=latest_name_keyword,
            content_type="application/json",
            forced_upload=True,
        )

        logger.info("Uploaded keyword engagement data")

    except Exception as ex:
        logger.error(
            "Engagement data pipeline failed: %s: %s",
            ex.__class__.__name__,
            str(ex),
            exc_info=True,
        )
