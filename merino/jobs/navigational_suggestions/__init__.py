"""CLI commands for the navigational_suggestions module"""

import base64
import json
import sys
import socket
import logging
from hashlib import md5
from typing import Optional, Any

import typer
from httpx import URL

from merino.configs import settings as config
from merino.jobs.navigational_suggestions.partner_favicons import PARTNER_FAVICONS
from merino.jobs.navigational_suggestions.utils import AsyncFaviconDownloader
from merino.utils.gcs.gcs_uploader import GcsUploader
from merino.jobs.utils.domain_category_mapping import DOMAIN_MAPPING
from merino.jobs.navigational_suggestions.domain_data_downloader import (
    DomainDataDownloader,
)
from merino.jobs.navigational_suggestions.domain_metadata_diff import DomainDiff
from merino.jobs.navigational_suggestions.domain_metadata_extractor import (
    DomainMetadataExtractor,
)
from merino.jobs.navigational_suggestions.domain_metadata_uploader import (
    DomainMetadataUploader,
)
from merino.providers.suggest.base import Category
from merino.utils.blocklists import TOP_PICKS_BLOCKLIST
from merino.jobs.navigational_suggestions.custom_favicons import get_custom_favicon_url

logger = logging.getLogger(__name__)

job_settings = config.jobs.navigational_suggestions

# Options
source_gcp_project_option = typer.Option(
    job_settings.source_gcp_project,
    "--src-gcp-project",
    help="GCP project to use for downloading the domain data",
)

destination_gcp_project_option = typer.Option(
    job_settings.destination_gcp_project,
    "--dst-gcp-project",
    help="GCP project to use to store the domain metadata on GCS for navigational suggestions",
)

destination_gcs_bucket_option = typer.Option(
    job_settings.destination_gcs_bucket,
    "--dst-gcs-bucket",
    help="GCS bucket where the domain metadata for navigational suggestions will be stored",
)

destination_gcs_cdn_hostname_option = typer.Option(
    job_settings.destination_cdn_hostname,
    "--dst-cdn-hostname",
    help="GCS cdn hostname where the domain metadata for navigational suggestions will be stored",
)

force_upload_option = typer.Option(
    job_settings.force_upload,
    "--force-upload",
    help="Upload the domain metadata to GCS bucket even if it already exists there",
)

write_xcom_option = typer.Option(
    False,
    "--write-xcom",
    help="Write job results to Airflow XCom File",
)

min_favicon_width_option = typer.Option(
    job_settings.min_favicon_width,
    "--min-favicon-width",
    help="Minimum width of the domain favicon required for it to be a part of domain metadata",
)

local_mode_option = typer.Option(
    False,
    "--local",
    help="Run in local mode using custom domains instead of BigQuery",
)

local_sample_size_option = typer.Option(
    20,
    "--sample-size",
    help="Number of domains to process in local mode",
)

local_data_option = typer.Option(
    "./local_data",
    "--metrics-dir",
    help="Directory to save local run metrics",
)

navigational_suggestions_cmd = typer.Typer(
    name="navigational-suggestions",
    help="Command for preparing top domain metadata for navigational suggestions",
)

monitor_option = typer.Option(
    False,
    "--monitor",
    help="Enable system monitoring during processing",
)


def _construct_top_picks(
    domain_data: list[dict],
    domain_metadata: list[dict[str, Optional[str]]],
) -> dict[str, list[dict[str, str]]]:
    result = []

    # Use zip to iterate over both lists together, stopping when either is exhausted
    # This prevents IndexError when domain_metadata is shorter than domain_data
    for domain, metadata in zip(domain_data, domain_metadata):
        if metadata["url"]:
            # We don't want to add custom-domains to the manifest file if they don't
            # have a valid favicon. We keep the "top-picks" ones (from BigQuery) because
            # they are used in Search & Suggest in the browser
            if metadata["icon"] == "" and domain.get("source") != "top-picks":
                continue

            domain_url = metadata["url"]
            result.append(
                {
                    "rank": domain["rank"],
                    "domain": metadata["domain"],
                    "categories": domain["categories"],
                    "serp_categories": _get_serp_categories(domain_url),
                    "url": domain_url,
                    "title": metadata["title"],
                    "icon": metadata["icon"],
                    "source": domain.get("source", "top-picks"),
                }
            )
    return {"domains": result}


def _construct_partner_manifest(
    partner_favicon_source: list[dict[str, str]],
    uploaded_favicons: list[str],
) -> dict[str, list[dict[str, str]]]:
    """Construct a list of processed partner favicons with their original and uploaded GCS URLs."""
    if len(partner_favicon_source) != len(uploaded_favicons):
        raise ValueError("Mismatch: The number of favicons and GCS URLs must be the same.")

    result = [
        {
            "domain": item["domain"],
            "url": item["url"],
            "original_icon_url": item["icon"],
            "gcs_icon_url": gcs_url,
        }
        for item, gcs_url in zip(partner_favicon_source, uploaded_favicons)
    ]

    return {"partners": result}


def _get_serp_categories(domain_url: str | None) -> list[int] | None:
    if domain_url:
        url = URL(domain_url)
        md5_hash = md5(url.host.encode(), usedforsecurity=False).digest()
        return [
            category.value
            for category in DOMAIN_MAPPING.get(
                base64.b64encode(md5_hash).decode(), [Category.Inconclusive]
            )
        ]
    return None


def _write_xcom_file(xcom_data: dict):
    with open("/airflow/xcom/return.json", "w") as file:
        json.dump(xcom_data, file)


async def _run_local_mode(
    local_sample_size: int, local_data_dir: str, min_favicon_width: int, enable_monitoring: bool
) -> None:
    """Run navigational suggestions in local mode"""
    import os
    import json
    from merino.jobs.navigational_suggestions.local_mode import (
        LocalDomainDataProvider,
        LocalMetricsCollector,
    )
    from merino.jobs.navigational_suggestions.custom_domains import CUSTOM_DOMAINS
    from google.cloud.storage import Client
    from google.auth.credentials import AnonymousCredentials

    # Convert typer.Option objects to actual values if needed
    sample_size = local_sample_size
    if hasattr(local_sample_size, "default"):
        sample_size = getattr(local_sample_size, "default", 50)

    data_dir = local_data_dir
    if hasattr(local_data_dir, "default"):
        data_dir = getattr(local_data_dir, "default", "./local_data")

    min_width = min_favicon_width
    if hasattr(min_favicon_width, "default"):
        min_width = getattr(min_favicon_width, "default", 48)

    enable_monitoring = enable_monitoring
    if hasattr(enable_monitoring, "default"):
        min_width = getattr(enable_monitoring, "default", False)

    logger.info("Running in LOCAL MODE with the following settings:")
    logger.info(f"- Sample size: {sample_size} domains")
    logger.info(f"- Data dir: {data_dir}")

    # 1. Setup components
    metrics_collector = LocalMetricsCollector(data_dir)

    domain_provider = LocalDomainDataProvider(
        custom_domains=CUSTOM_DOMAINS, sample_size=sample_size
    )
    domain_data = domain_provider.get_domain_data()
    logger.info(f"Domain data loaded: {len(domain_data)} domains")

    # 2. Setup GCS emulator
    gcs_endpoint = "http://localhost:4443"
    bucket_name = "merino-test-bucket"
    cdn_hostname = "localhost:4443"

    # Check if the GCS emulator is running before proceeding
    # Add a small initial delay to make sure the log messages are flushed
    logger.info("Checking if GCS emulator is running...")

    try:
        # Try directly connecting to the socket with a very short timeout
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.5)  # 500ms timeout
        result = sock.connect_ex(("localhost", 4443))
        sock.close()

        if result != 0:
            error_message = (
                "ERROR: GCS emulator is not running at localhost:4443. "
                "Please start the container using ./dev/start-local-gcs-emulator.sh"
            )
            logger.error(error_message)
            sys.exit(1)

        logger.info("GCS emulator is running")
    except Exception as e:
        error_message = (
            f"ERROR: Failed to connect to GCS emulator: {e}. "
            "Please start the container using ./dev/start-local-gcs-emulator.sh"
        )
        logger.error(error_message)
        sys.exit(1)

    os.environ["STORAGE_EMULATOR_HOST"] = gcs_endpoint

    try:
        # Connect to fake-gcs-server
        storage_client = Client(project="test-project", credentials=AnonymousCredentials())  # type: ignore

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

        domain_metadata_uploader = DomainMetadataUploader(
            force_upload=True,
            uploader=gcs_uploader,
            async_favicon_downloader=AsyncFaviconDownloader(),
        )
    except Exception as e:
        error_message = (
            f"ERROR: Failed to connect to GCS emulator at {gcs_endpoint}: {e}\n"
            "Please start the container using ./dev/start-local-gcs-emulator.sh"
        )
        logger.error(error_message)
        sys.exit(1)

    # 3. Setup domain metadata extractor with metrics collection
    domain_metadata_extractor = DomainMetadataExtractor(blocked_domains=TOP_PICKS_BLOCKLIST)

    # Add metrics collection
    original_process_method = domain_metadata_extractor._process_single_domain

    async def _process_with_metrics(
        domain_data: dict[str, Any], min_width: int, uploader: DomainMetadataUploader
    ) -> dict[str, Optional[str]]:
        try:
            # Check if this domain has a custom favicon
            domain = domain_data.get("domain", "")
            has_custom_favicon = bool(get_custom_favicon_url(domain))

            result = await original_process_method(domain_data, min_width, uploader)

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

    # Type checker will complain about this, but it works at runtime
    # We're monkey patching the method for local metrics collection
    setattr(domain_metadata_extractor, "_process_single_domain", _process_with_metrics)

    # 4. Process domains
    domain_metadata = domain_metadata_extractor.process_domain_metadata(
        domain_data,
        min_width,
        uploader=domain_metadata_uploader,
        enable_monitoring=enable_monitoring,
    )
    logger.info("Domain metadata extraction complete")

    # 5. Process partner favicons
    partner_favicons = [item["icon"] for item in PARTNER_FAVICONS]
    uploaded_partner_favicons = await domain_metadata_uploader.upload_favicons(partner_favicons)
    logger.info("Partner favicons uploaded to GCS")

    # 6. Construct top picks content
    top_picks = _construct_top_picks(domain_data, domain_metadata)
    partner_manifest = _construct_partner_manifest(PARTNER_FAVICONS, uploaded_partner_favicons)
    final_top_picks = {**top_picks, **partner_manifest}

    if not final_top_picks:
        final_top_picks = {"domains": []}

    # 7. Save top picks
    try:
        # Upload to GCS emulator
        top_picks_json = json.dumps(final_top_picks, indent=4)
        top_pick_blob = domain_metadata_uploader.upload_top_picks(top_picks_json)

        # Save local copy
        os.makedirs(local_data_dir, exist_ok=True)
        local_file = os.path.join(local_data_dir, "top_picks_latest.json")
        with open(local_file, "w") as f:
            f.write(top_picks_json)
    except Exception as e:
        logger.error(f"Error uploading top picks: {e}")
        # Fallback to local file
        os.makedirs(local_data_dir, exist_ok=True)
        local_file = os.path.join(local_data_dir, "top_picks_latest.json")
        with open(local_file, "w") as f:
            f.write(json.dumps(final_top_picks, indent=4))

        class MockBlob:
            """Mock for GCS blob in local mode"""

            name: str
            public_url: str

            def __init__(self):
                self.name = "top_picks_latest.json"
                self.public_url = f"file://{local_file}"

        # We've declared the MockBlob class inline, so type checker won't recognize it
        top_pick_blob = MockBlob()  # type: ignore

    # 8. Save metrics and show results
    metrics_collector.save_report()

    # Show results
    logger.info("=" * 40)
    logger.info("TOP PICKS FILE:")
    logger.info(f"GCS URL: {top_pick_blob.public_url}")

    direct_url = (
        f"http://localhost:4443/storage/v1/b/{bucket_name}/o/{top_pick_blob.name}?alt=media"
    )
    logger.info(f"Direct URL: {direct_url}")

    local_file = os.path.join(local_data_dir, "top_picks_latest.json")
    if os.path.exists(local_file):
        logger.info(f"Local copy: {local_file}")

    logger.info("=" * 40)


async def _run_normal_mode(
    source_gcp_project: str,
    destination_gcp_project: str,
    destination_gcs_bucket: str,
    destination_cdn_hostname: str,
    force_upload: bool,
    write_xcom: bool,
    min_favicon_width: int,
    enable_monitoring: bool = False,
) -> None:
    """Prepare domain metadata for navigational suggestions"""
    # download top domains data
    domain_data_downloader = DomainDataDownloader(source_gcp_project)
    domain_data = domain_data_downloader.download_data()
    logger.info("domain data download complete")

    # Create uploader to download favicons and upload  them to Google Cloud afterwards
    domain_metadata_uploader = DomainMetadataUploader(
        force_upload,
        GcsUploader(
            destination_gcp_project,
            destination_gcs_bucket,
            destination_cdn_hostname,
        ),
        AsyncFaviconDownloader(),
    )

    # extract domain metadata of top domains and upload the best favicon for each immediately
    domain_metadata_extractor = DomainMetadataExtractor(blocked_domains=TOP_PICKS_BLOCKLIST)
    domain_metadata: list[dict[str, Optional[str]]] = (
        domain_metadata_extractor.process_domain_metadata(
            domain_data,
            min_favicon_width,
            uploader=domain_metadata_uploader,
            enable_monitoring=enable_monitoring,
        )
    )
    logger.info("domain metadata extraction complete")

    # Process partner favicons
    partner_favicons = [item["icon"] for item in PARTNER_FAVICONS]
    uploaded_partner_favicons = await domain_metadata_uploader.upload_favicons(partner_favicons)
    logger.info("partner favicons uploaded to GCS")

    # construct top pick contents. The `domain_metadata` already has the uploaded favicon URL in it
    top_picks = _construct_top_picks(domain_data, domain_metadata)

    # construct partner contents
    partner_manifest = _construct_partner_manifest(PARTNER_FAVICONS, uploaded_partner_favicons)
    final_top_picks = {**top_picks, **partner_manifest}

    # Create diff class for comparison of Top Picks Files
    old_top_picks: dict[str, list[dict[str, str]]] | None = (
        domain_metadata_uploader.get_latest_file_for_diff()
    )

    if old_top_picks is None:
        old_top_picks = {}

    domain_diff = DomainDiff(latest_domain_data=final_top_picks, old_domain_data=old_top_picks)
    (
        unchanged,
        added_domains,
        added_urls,
    ) = domain_diff.compare_top_picks(
        new_top_picks=final_top_picks,
        old_top_picks=old_top_picks,
    )

    # Upload new domain file to replace old now that data is acquired for compare.
    top_pick_blob = domain_metadata_uploader.upload_top_picks(
        json.dumps(final_top_picks, indent=4)
    )
    diff: dict = domain_diff.create_diff(
        file_name=top_pick_blob.name,
        unchanged=unchanged,
        domains=added_domains,
        urls=added_urls,
    )
    logger.info(
        "top pick contents uploaded to GCS",
        extra={"public_url": top_pick_blob.public_url},
    )

    if write_xcom is True:
        _write_xcom_file({"top_pick_url": top_pick_blob.public_url, "diff": diff})


@navigational_suggestions_cmd.command()
async def prepare_domain_metadata(
    source_gcp_project: str = source_gcp_project_option,
    destination_gcp_project: str = destination_gcp_project_option,
    destination_gcs_bucket: str = destination_gcs_bucket_option,
    destination_cdn_hostname: str = destination_gcs_cdn_hostname_option,
    force_upload: bool = force_upload_option,
    write_xcom: bool = write_xcom_option,
    min_favicon_width: int = min_favicon_width_option,
    local_mode: bool = local_mode_option,
    local_sample_size: int = local_sample_size_option,
    local_data_dir: str = local_data_option,
    enable_monitoring: bool = monitor_option,
):
    """Prepare domain metadata for navigational suggestions"""
    # Unwrap typer.Option objects to get their default values if present
    src_project = getattr(source_gcp_project, "default", source_gcp_project)
    dst_project = getattr(destination_gcp_project, "default", destination_gcp_project)
    dst_bucket = getattr(destination_gcs_bucket, "default", destination_gcs_bucket)
    dst_cdn = getattr(destination_cdn_hostname, "default", destination_cdn_hostname)
    force = getattr(force_upload, "default", force_upload)
    write_x = getattr(write_xcom, "default", write_xcom)
    min_width = getattr(min_favicon_width, "default", min_favicon_width)
    sample_size = getattr(local_sample_size, "default", local_sample_size)
    data_dir = getattr(local_data_dir, "default", local_data_dir)
    enable_monitoring = getattr(enable_monitoring, "default", enable_monitoring)

    # Run the appropriate mode
    if local_mode:
        # Local mode for development and testing
        # This mode uses fake-gcs-server and custom domains
        # instead of connecting to Google Cloud
        await _run_local_mode(sample_size, data_dir, min_width, enable_monitoring)
    else:
        # Normal mode used in production
        # This connects to Google Cloud and processes custom_domains
        # AND domains from BigQuery
        await _run_normal_mode(
            src_project,
            dst_project,
            dst_bucket,
            dst_cdn,
            force,
            write_x,
            min_width,
            enable_monitoring,
        )
