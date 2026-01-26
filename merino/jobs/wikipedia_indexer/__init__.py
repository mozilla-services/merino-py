"""CLI commands for the wikipedia_indexer module"""

import logging
from typing import Annotated

import typer

from merino.configs import settings as config
from merino.jobs.wikipedia_indexer.filemanager import FileManager
from merino.jobs.wikipedia_indexer.indexer import Indexer
from merino.jobs.wikipedia_indexer.utils import create_blocklist
from merino.search.elastic import ElasticSearchAdapter
from merino.utils.blocklists import WIKIPEDIA_TITLE_BLOCKLIST

logger = logging.getLogger(__name__)

job_settings = config.jobs.wikipedia_indexer


# Shared options
gcs_path_option = typer.Option(
    job_settings.gcs_path,
    "--gcs-path",
    help="Full GCS path to the folder containing Wikipedia exports",
)

gcp_project_option = typer.Option(
    job_settings.gcp_project,
    "--gcp-project",
    help="GCP project to use for GCS",
)


version_option = typer.Option(job_settings.index_version, "--version", help="Version of the index")


indexer_cmd = typer.Typer(
    name="wikipedia-indexer",
    help="Commands for indexing Wikipedia exports into Elasticsearch",
)


@indexer_cmd.command()
def index(
    language: Annotated[
        str, typer.Option(help="Language to index (e.g., en, fr, de), default to en.")
    ] = "en",
    elasticsearch_url: str = job_settings.es_url,
    elasticsearch_api_key: str = job_settings.es_api_key,
    blocklist_file_url: str = job_settings.blocklist_file_url,
    index_version: str = version_option,
    total_docs: int = job_settings.total_docs,
    gcs_path: str = gcs_path_option,
    gcp_project: str = gcp_project_option,
):
    """Index file from GCS to Elasticsearch"""
    elasticsearch = ElasticSearchAdapter(url=elasticsearch_url, api_key=elasticsearch_api_key)

    blocklist = create_blocklist(
        blocklist_file_url
    )  # TODO Re-using same blocklist for now until we figure something else out

    logger.info(f"Starting Wikipedia indexing for language: {language}")

    file_manager = FileManager(gcs_path, gcp_project, "", language)

    alias_key = f"{language}_es_alias"
    elasticsearch_alias = job_settings[alias_key]

    indexer = Indexer(
        index_version,
        blocklist,
        WIKIPEDIA_TITLE_BLOCKLIST,
        file_manager,
        elasticsearch,
    )
    indexer.index_from_export(total_docs, elasticsearch_alias)


@indexer_cmd.command()
def copy_export(
    language: Annotated[
        str,
        typer.Option(help="Language to copy export for (e.g., en, fr, de), default to en."),
    ] = "en",
    export_base_url: str = job_settings.export_base_url,
    gcs_path: str = gcs_path_option,
    gcp_project: str = gcp_project_option,
):
    """Copy file from Wikimedia to GCS"""
    file_manager = FileManager(gcs_path, gcp_project, export_base_url, language)

    logger.info(
        f"Ensuring latest {language} dump is on GCS",
        extra={"gcs_path": gcs_path, "gcp_project": gcp_project},
    )
    latest = file_manager.stream_latest_dump_to_gcs()
    if latest is None or not getattr(latest, "name", ""):
        raise RuntimeError(
            f"No {language} CirrusSearch dump found in current/ or fallback (20251027)."
        )
