"""CLI commands for the navigational_suggestions module"""

import base64
import json
import logging
from hashlib import md5
from typing import Optional

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

navigational_suggestions_cmd = typer.Typer(
    name="navigational-suggestions",
    help="Command for preparing top domain metadata for navigational suggestions",
)


def _construct_top_picks(
    domain_data: list[dict],
    favicons: list[str],
    domain_metadata: list[dict[str, Optional[str]]],
) -> dict[str, list[dict[str, str]]]:
    result = []
    for index, domain in enumerate(domain_data):
        if domain_metadata[index]["url"]:
            domain_url = domain_metadata[index]["url"]
            result.append(
                {
                    "rank": domain["rank"],
                    "domain": domain_metadata[index]["domain"],
                    "categories": domain["categories"],
                    "serp_categories": _get_serp_categories(domain_url),
                    "url": domain_url,
                    "title": domain_metadata[index]["title"],
                    "icon": favicons[index],
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


@navigational_suggestions_cmd.command()
def prepare_domain_metadata(
    source_gcp_project: str = source_gcp_project_option,
    destination_gcp_project: str = destination_gcp_project_option,
    destination_gcs_bucket: str = destination_gcs_bucket_option,
    destination_cdn_hostname: str = destination_gcs_cdn_hostname_option,
    force_upload: bool = force_upload_option,
    write_xcom: bool = write_xcom_option,
    min_favicon_width: int = min_favicon_width_option,
):
    """Prepare domain metadata for navigational suggestions"""
    # download top domains data
    domain_data_downloader = DomainDataDownloader(source_gcp_project)
    domain_data = domain_data_downloader.download_data()
    logger.info("domain data download complete")

    # extract domain metadata of top domains
    domain_metadata_extractor = DomainMetadataExtractor(blocked_domains=TOP_PICKS_BLOCKLIST)
    domain_metadata: list[dict[str, Optional[str]]] = (
        domain_metadata_extractor.get_domain_metadata(domain_data, min_favicon_width)
    )
    logger.info("domain metadata extraction complete")

    # upload favicons and get their public urls
    domain_metadata_uploader = DomainMetadataUploader(
        force_upload,
        GcsUploader(
            destination_gcp_project,
            destination_gcs_bucket,
            destination_cdn_hostname,
        ),
        AsyncFaviconDownloader(),
    )

    # Process top picks favicons
    top_picks_favicons = [str(metadata["icon"]) for metadata in domain_metadata]
    uploaded_top_picks_favicons = domain_metadata_uploader.upload_favicons(top_picks_favicons)
    logger.info("top picks favicons uploaded to GCS")

    # Process partner favicons
    partner_favicons = [item["icon"] for item in PARTNER_FAVICONS]
    uploaded_partner_favicons = domain_metadata_uploader.upload_favicons(partner_favicons)
    logger.info("partner favicons uploaded to GCS")

    # construct top pick contents
    top_picks = _construct_top_picks(domain_data, uploaded_top_picks_favicons, domain_metadata)

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
