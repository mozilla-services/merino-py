"""CLI commands for the navigational_suggestions module"""
import json
import logging
from typing import Optional

import typer

from merino.config import settings as config
from merino.jobs.navigational_suggestions.domain_data_downloader import (
    DomainDataDownloader,
)
from merino.jobs.navigational_suggestions.domain_metadata_extractor import (
    DomainMetadataExtractor,
)
from merino.jobs.navigational_suggestions.domain_metadata_uploader import (
    DomainMetadataUploader,
)
from merino.jobs.navigational_suggestions.utils import (
    update_top_picks_with_firefox_favicons,
)

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
            result.append(
                {
                    "rank": domain["rank"],
                    "domain": domain_metadata[index]["domain"],
                    "categories": domain["categories"],
                    "url": domain_metadata[index]["url"],
                    "title": domain_metadata[index]["title"],
                    "icon": favicons[index],
                }
            )
    return {"domains": result}


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
    domain_metadata_extractor = DomainMetadataExtractor()
    domain_metadata: list[
        dict[str, Optional[str]]
    ] = domain_metadata_extractor.get_domain_metadata(domain_data, min_favicon_width)
    logger.info("domain metadata extraction complete")

    # upload favicons and get their public urls
    domain_metadata_uploader = DomainMetadataUploader(
        destination_gcp_project,
        destination_gcs_bucket,
        destination_cdn_hostname,
        force_upload,
    )
    favicons = [str(metadata["icon"]) for metadata in domain_metadata]
    uploaded_favicons = domain_metadata_uploader.upload_favicons(favicons)
    logger.info("domain favicons uploaded to gcs")

    # construct top pick contents, update them with firefox packaged favicons and upload to gcs
    top_picks = _construct_top_picks(domain_data, uploaded_favicons, domain_metadata)
    update_top_picks_with_firefox_favicons(top_picks)
    top_pick_blob = domain_metadata_uploader.upload_top_picks(
        json.dumps(top_picks, indent=4)
    )
    logger.info(
        "top pick contents uploaded to gcs",
        extra={"public_url": top_pick_blob.public_url},
    )
    if write_xcom is True:
        _write_xcom_file({"top_pick_url": top_pick_blob.public_url})
