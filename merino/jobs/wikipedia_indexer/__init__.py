"""CLI commands for the wikipedia_indexer module"""
import logging

import typer
from elasticsearch import Elasticsearch

from merino.config import settings as config
from merino.jobs.wikipedia_indexer.filemanager import FileManager
from merino.jobs.wikipedia_indexer.indexer import Indexer
from merino.jobs.wikipedia_indexer.util import create_blocklist

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


version_option = typer.Option(
    job_settings.index_version, "--version", help="Version of the index"
)


indexer_cmd = typer.Typer(
    name="wikipedia-indexer",
    help="Commands for indexing Wikipedia exports into Elasticsearch",
)


@indexer_cmd.command()
def index(
    elasticsearch_cloud_id: str = job_settings.es_cloud_id,
    elasticsearch_api_key: str = job_settings.es_api_key,
    elasticsearch_alias: str = job_settings.es_alias,
    blocklist_file_url: str = job_settings.blocklist_file_url,
    index_version: str = version_option,
    total_docs: int = job_settings.total_docs,
    gcs_path: str = gcs_path_option,
    gcp_project: str = gcp_project_option,
):
    """Index file from GCS to Elasticsearch"""
    es_client = Elasticsearch(
        cloud_id=elasticsearch_cloud_id,
        api_key=elasticsearch_api_key,
        request_timeout=60,
    )

    file_manager = FileManager(gcs_path, gcp_project, "")

    blocklist = create_blocklist(blocklist_file_url)

    indexer = Indexer(
        index_version,
        blocklist,
        file_manager,
        es_client,
    )
    indexer.index_from_export(total_docs, elasticsearch_alias)


@indexer_cmd.command()
def copy_export(
    export_base_url: str = job_settings.export_base_url,
    gcs_path: str = gcs_path_option,
    gcp_project: str = gcp_project_option,
):
    """Copy file from Wikimedia to GCS"""
    file_manager = FileManager(gcs_path, gcp_project, export_base_url)

    logger.info(
        "Ensuring latest dump is on GCS",
        extra={"gcs_path": gcs_path, "gcp_project": gcp_project},
    )
    latest = file_manager.stream_latest_dump_to_gcs()
    if not latest.name:
        raise RuntimeError("Unable to ensure latest dump on GCS or missing file name.")
