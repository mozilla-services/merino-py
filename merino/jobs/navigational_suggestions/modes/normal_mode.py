"""Production mode for navigational suggestions job"""

import json
import logging

from merino.jobs.navigational_suggestions.io.domain_data_downloader import DomainDataDownloader
from merino.jobs.navigational_suggestions.io.domain_metadata_diff import DomainDiff
from merino.jobs.navigational_suggestions.io.domain_metadata_uploader import DomainMetadataUploader
from merino.jobs.navigational_suggestions.processing.domain_processor import DomainProcessor
from merino.jobs.navigational_suggestions.processing.manifest_builder import (
    construct_errors_manifest,
    construct_partner_manifest,
    construct_top_picks,
)
from merino.jobs.navigational_suggestions.enrichments.partner_favicons import PARTNER_FAVICONS
from merino.jobs.navigational_suggestions.io import AsyncFaviconDownloader
from merino.utils.blocklists import TOP_PICKS_BLOCKLIST
from merino.utils.gcs.gcs_uploader import GcsUploader

logger = logging.getLogger(__name__)


def write_xcom_file(xcom_data: dict) -> None:
    """Write job results to Airflow XCom file."""
    with open("/airflow/xcom/return.json", "w") as file:
        json.dump(xcom_data, file)


def run_normal_mode(
    source_gcp_project: str,
    destination_gcp_project: str,
    destination_gcs_bucket: str,
    destination_cdn_hostname: str,
    force_upload: bool,
    write_xcom: bool,
    min_favicon_width: int,
    enable_monitoring: bool = False,
) -> None:
    """Run in production mode: fetch domains from BigQuery, extract metadata, upload to GCS."""
    logger.info("Running in NORMAL MODE (production)")

    # Step 1: Download top domains data from BigQuery
    domain_data_downloader = DomainDataDownloader(source_gcp_project)
    domain_data = domain_data_downloader.download_data()
    logger.info("Domain data download complete")

    # Step 2: Create uploader for favicons and metadata
    domain_metadata_uploader = DomainMetadataUploader(
        force_upload,
        GcsUploader(
            destination_gcp_project,
            destination_gcs_bucket,
            destination_cdn_hostname,
        ),
        AsyncFaviconDownloader(),
    )

    # Step 3: Extract domain metadata and upload favicons
    domain_processor = DomainProcessor(blocked_domains=TOP_PICKS_BLOCKLIST)
    domain_metadata = domain_processor.process_domain_metadata(
        domain_data,
        min_favicon_width,
        uploader=domain_metadata_uploader,
        enable_monitoring=enable_monitoring,
    )
    logger.info("Domain metadata extraction complete")

    # Step 4: Process partner favicons
    partner_favicons = [item["icon"] for item in PARTNER_FAVICONS]
    uploaded_partner_favicons = domain_metadata_uploader.upload_favicons(partner_favicons)
    logger.info("Partner favicons uploaded to GCS")

    # Step 5: Construct top picks manifest
    top_picks = construct_top_picks(domain_data, domain_metadata)

    # Step 5b: Construct errors manifest for domains that failed
    errors_manifest = construct_errors_manifest(domain_data, domain_metadata)
    logger.info(f"Found {len(errors_manifest['errors'])} domains with favicon extraction errors")

    # Step 6: Construct partner manifest
    partner_manifest = construct_partner_manifest(PARTNER_FAVICONS, uploaded_partner_favicons)
    final_top_picks = {**top_picks, **partner_manifest}

    # Step 7: Create diff comparing old and new data
    old_top_picks = domain_metadata_uploader.get_latest_file_for_diff()
    if old_top_picks is None:
        old_top_picks = {"domains": []}

    domain_diff = DomainDiff(latest_domain_data=final_top_picks, old_domain_data=old_top_picks)
    (
        unchanged,
        added_domains,
        added_urls,
    ) = domain_diff.compare_top_picks(
        new_top_picks=final_top_picks,
        old_top_picks=old_top_picks,
    )

    # Step 8: Upload new domain file to GCS
    top_pick_blob = domain_metadata_uploader.upload_top_picks(
        json.dumps(final_top_picks, indent=4)
    )
    diff = domain_diff.create_diff(
        file_name=top_pick_blob.name or "",
        unchanged=unchanged,
        domains=added_domains,
        urls=added_urls,
    )
    logger.info(
        "Top pick contents uploaded to GCS",
        extra={"public_url": top_pick_blob.public_url},
    )

    # Step 8b: Upload errors manifest to GCS
    errors_blob = domain_metadata_uploader.upload_errors(json.dumps(errors_manifest, indent=4))
    logger.info(
        "Errors manifest uploaded to GCS",
        extra={"public_url": errors_blob.public_url},
    )

    # Step 9: Write XCom file if requested (for Airflow integration)
    if write_xcom:
        write_xcom_file({"top_pick_url": top_pick_blob.public_url, "diff": diff})
