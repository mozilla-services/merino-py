"""Local development mode for navigational suggestions job"""

import json
import logging
import os
import socket
import sys
from typing import Any, Optional, Union

import tldextract
from google.auth.credentials import AnonymousCredentials
from google.cloud.storage import Blob, Client

from merino.jobs.navigational_suggestions.enrichments.custom_domains import CUSTOM_DOMAINS
from merino.jobs.navigational_suggestions.enrichments.custom_favicons import get_custom_favicon_url
from merino.jobs.navigational_suggestions.io.domain_metadata_uploader import DomainMetadataUploader
from merino.jobs.navigational_suggestions.processing.domain_processor import DomainProcessor
from merino.jobs.navigational_suggestions.modes.local_mode_helpers import (
    LocalDomainDataProvider,
    LocalMetricsCollector,
)
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


class MockBlob:
    """Mock for GCS blob in local mode."""

    def __init__(self, name: str, local_path: str):
        self.name = name
        self.public_url = f"file://{local_path}"


def check_gcs_emulator_running() -> bool:
    """Check if GCS emulator is running at localhost:4443."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.5)  # 500ms timeout
        result = sock.connect_ex(("localhost", 4443))
        sock.close()
        return result == 0
    except Exception:
        return False


def setup_gcs_emulator(bucket_name: str, cdn_hostname: str) -> tuple[GcsUploader, Client]:
    """Connect to GCS emulator and create bucket if needed."""
    gcs_endpoint = "http://localhost:4443"
    os.environ["STORAGE_EMULATOR_HOST"] = gcs_endpoint

    logger.info("Checking if GCS emulator is running...")

    if not check_gcs_emulator_running():
        error_message = (
            "ERROR: GCS emulator is not running at localhost:4443. "
            "Please start it with: make docker-compose-up"
        )
        logger.error(error_message)
        sys.exit(1)

    logger.info("GCS emulator is running")

    try:
        # Connect to fake-gcs-server
        storage_client = Client(project="test-project", credentials=AnonymousCredentials())  # type: ignore[no-untyped-call]

        bucket = storage_client.bucket(bucket_name)
        if not bucket.exists():
            logger.info(f"Creating bucket {bucket_name} in fake-gcs-server")
            bucket = storage_client.create_bucket(bucket_name)

        # Setup uploader
        gcs_uploader = GcsUploader(
            destination_gcp_project="test-project",
            destination_bucket_name=bucket_name,
            destination_cdn_hostname=cdn_hostname,
        )

        return gcs_uploader, storage_client

    except Exception as e:
        error_message = (
            f"ERROR: Failed to connect to GCS emulator at {gcs_endpoint}: {e}\n"
            "Please start it with: docker compose -f dev/docker-compose.yaml up -d fake-gcs"
        )
        logger.error(error_message)
        sys.exit(1)


def create_metrics_aware_processor(
    domain_processor: DomainProcessor,
    metrics_collector: LocalMetricsCollector,
) -> DomainProcessor:
    """Wrap domain processor to collect metrics during processing."""
    # Store the original method
    original_method = domain_processor._process_single_domain

    async def _process_with_metrics(
        domain_data: dict[str, Any], min_width: int, uploader: DomainMetadataUploader
    ) -> dict[str, Optional[str]]:
        try:
            # Check if this domain has a custom favicon
            domain = domain_data.get("domain", "")
            second_level = tldextract.extract(domain).domain if domain else ""
            has_custom_favicon = bool(get_custom_favicon_url(second_level))

            result = await original_method(domain_data, min_width, uploader)

            # Determine if custom favicon was actually used
            used_custom = has_custom_favicon and bool(result.get("icon"))

            metrics_collector.record_domain_result(domain_data["domain"], result, used_custom)
            return result
        except Exception as e:
            logger.error(f"Error processing domain {domain_data['domain']}: {e}")
            empty_result: dict[str, Optional[str]] = {
                "url": None,
                "title": None,
                "icon": None,
                "domain": None,
            }
            metrics_collector.record_domain_result(domain_data["domain"], empty_result, False)
            return empty_result

    # Monkey patch the method for local metrics collection
    setattr(domain_processor, "_process_single_domain", _process_with_metrics)

    return domain_processor


def save_top_picks_locally(
    final_top_picks: dict,
    data_dir: str,
    bucket_name: str,
    uploader: DomainMetadataUploader,
) -> Union[Blob, MockBlob]:
    """Save top picks locally and try uploading to GCS emulator."""
    top_picks_json = json.dumps(final_top_picks, indent=4)

    # Ensure directory exists
    os.makedirs(data_dir, exist_ok=True)
    local_file = os.path.join(data_dir, "top_picks_latest.json")

    try:
        # Try to upload to GCS emulator
        top_pick_blob = uploader.upload_top_picks(top_picks_json)

        # Also save local copy
        with open(local_file, "w") as f:
            f.write(top_picks_json)

        return top_pick_blob

    except Exception as e:
        logger.error(f"Error uploading top picks: {e}")

        # Fallback to local file only
        with open(local_file, "w") as f:
            f.write(top_picks_json)

        return MockBlob("top_picks_latest.json", local_file)


def run_local_mode(
    local_sample_size: int,
    local_data_dir: str,
    min_favicon_width: int,
    enable_monitoring: bool,
) -> None:
    """Run in local mode: uses custom domains and fake-gcs-server for testing."""
    logger.info("=" * 60)
    logger.info("Running in LOCAL MODE")
    logger.info("=" * 60)
    logger.info(f"Sample size: {local_sample_size} domains")
    logger.info(f"Data directory: {local_data_dir}")
    logger.info(f"Min favicon width: {min_favicon_width}")
    logger.info(f"Monitoring enabled: {enable_monitoring}")
    logger.info("=" * 60)

    # Step 1: Setup components
    metrics_collector = LocalMetricsCollector(local_data_dir)
    domain_provider = LocalDomainDataProvider(
        custom_domains=CUSTOM_DOMAINS, sample_size=local_sample_size
    )
    domain_data = domain_provider.get_domain_data()
    logger.info(f"Domain data loaded: {len(domain_data)} domains")

    # Step 2: Setup GCS emulator
    bucket_name = "merino-test-bucket"
    cdn_hostname = "localhost:4443"

    gcs_uploader, storage_client = setup_gcs_emulator(bucket_name, cdn_hostname)

    domain_metadata_uploader = DomainMetadataUploader(
        force_upload=True,
        uploader=gcs_uploader,
        async_favicon_downloader=AsyncFaviconDownloader(),
    )

    # Step 3: Setup domain processor with metrics collection
    domain_processor = DomainProcessor(blocked_domains=TOP_PICKS_BLOCKLIST)
    domain_processor = create_metrics_aware_processor(domain_processor, metrics_collector)

    # Step 4: Process domains
    logger.info("Starting domain processing...")
    domain_metadata = domain_processor.process_domain_metadata(
        domain_data,
        min_favicon_width,
        uploader=domain_metadata_uploader,
        enable_monitoring=enable_monitoring,
    )
    logger.info("Domain metadata extraction complete")

    # Step 5: Process partner favicons
    partner_favicons = [item["icon"] for item in PARTNER_FAVICONS]
    uploaded_partner_favicons = domain_metadata_uploader.upload_favicons(partner_favicons)
    logger.info("Partner favicons uploaded to GCS")

    # Step 6: Construct top picks content
    top_picks = construct_top_picks(domain_data, domain_metadata)
    partner_manifest = construct_partner_manifest(PARTNER_FAVICONS, uploaded_partner_favicons)
    final_top_picks = {**top_picks, **partner_manifest}

    if not final_top_picks:
        final_top_picks = {"domains": []}

    # Step 6b: Construct errors manifest
    errors_manifest = construct_errors_manifest(domain_data, domain_metadata)
    logger.info(f"Found {len(errors_manifest['errors'])} domains with favicon extraction errors")

    # Step 7: Save top picks
    top_pick_blob = save_top_picks_locally(
        final_top_picks, local_data_dir, bucket_name, domain_metadata_uploader
    )

    # Step 7b: Save errors manifest
    errors_json = json.dumps(errors_manifest, indent=4)
    errors_file = os.path.join(local_data_dir, "errors_latest.json")
    with open(errors_file, "w") as f:
        f.write(errors_json)
    logger.info(f"Errors manifest saved to: {errors_file}")

    # Step 8: Save metrics and show results
    metrics_collector.save_report()

    # Display results
    logger.info("=" * 60)
    logger.info("LOCAL MODE COMPLETE - RESULTS")
    logger.info("=" * 60)
    logger.info(f"Top Picks File: {top_pick_blob.name}")
    logger.info(f"Public URL: {top_pick_blob.public_url}")
    logger.info(f"Errors File: {errors_file}")

    direct_url = (
        f"http://localhost:4443/storage/v1/b/{bucket_name}/o/{top_pick_blob.name}?alt=media"
    )
    logger.info(f"Direct URL: {direct_url}")

    local_file = os.path.join(local_data_dir, "top_picks_latest.json")
    if os.path.exists(local_file):
        logger.info(f"Local copy: {local_file}")

    logger.info(f"Metrics saved to: {local_data_dir}")
    logger.info("=" * 60)
