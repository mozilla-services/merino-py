"""CLI commands for the navigational_suggestions module"""
import json
import logging

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
    help="Upload the domain metadata to GCS bucket even if it aleady exists there",
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
    urls_and_titles: list[dict],
    second_level_domains: list[str],
) -> str:
    result = []
    for index, domain in enumerate(domain_data):
        result.append(
            {
                "rank": domain["rank"],
                "domain": second_level_domains[index],
                "categories": domain["categories"],
                **urls_and_titles[index],
                "icon": favicons[index],
            }
        )
    top_picks = {"domains": result}
    return json.dumps(top_picks, indent=4)


@navigational_suggestions_cmd.command()
def prepare_domain_metadata(
    source_gcp_project: str = source_gcp_project_option,
    destination_gcp_project: str = destination_gcp_project_option,
    destination_gcs_bucket: str = destination_gcs_bucket_option,
    destination_cdn_hostname: str = destination_gcs_cdn_hostname_option,
    force_upload: bool = force_upload_option,
    min_favicon_width: int = min_favicon_width_option,
):
    """Prepare domain metadata for navigational suggestions"""
    # download top domains data
    domain_data_downloader = DomainDataDownloader(source_gcp_project)
    domain_data = domain_data_downloader.download_data()
    logger.info("domain data download complete")

    # extract domain metadata of top domains
    domain_metadata_extractor = DomainMetadataExtractor()
    favicons = domain_metadata_extractor.get_favicons(domain_data, min_favicon_width)
    urls_and_titles = domain_metadata_extractor.get_urls_and_titles(domain_data)
    second_level_domains = domain_metadata_extractor.get_second_level_domains(
        domain_data
    )
    logger.info("domain metadata extraction complete")

    # upload favicons and get their public urls
    domain_metadata_uploader = DomainMetadataUploader(
        destination_gcp_project,
        destination_gcs_bucket,
        destination_cdn_hostname,
        force_upload,
    )
    uploaded_favicons = domain_metadata_uploader.upload_favicons(favicons)
    logger.info("domain favicons uploaded to gcs")

    # construct top pick contents and upload it to gcs
    top_picks = _construct_top_picks(
        domain_data, uploaded_favicons, urls_and_titles, second_level_domains
    )
    domain_metadata_uploader.upload_top_picks(top_picks)
    logger.info("top pick contents uploaded to gcs")
