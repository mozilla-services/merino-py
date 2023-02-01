"""CLI commands for the wikipedia_indexer module"""
import logging

import typer
from elasticsearch import Elasticsearch

from merino.config import settings as config
from merino.jobs.wikipedia_indexer.filemanager import FileManager
from merino.jobs.wikipedia_indexer.indexer import Indexer

logger = logging.getLogger(__name__)

es_settings = config.providers.wikipedia
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
    help="GCP project to use for gcs",
)

indexer_cmd = typer.Typer(
    name="wikipedia-indexer",
    help="Commands for indexing wikipedia exports into elasticsearch",
)


@indexer_cmd.command()
def index(
    elasticsearch_hostname: str = es_settings.es_url,
    elasticsearch_cloud_id: str = es_settings.es_cloud_id,
    elasticsearch_alias: str = es_settings.es_index,
    elasticsearch_username: str = es_settings.es_user,
    elasticsearch_password: str = es_settings.es_password,
    index_version: str = job_settings.index_version,
    total_docs: int = job_settings.total_docs,
    gcs_path: str = gcs_path_option,
    gcp_project: str = gcp_project_option,
):
    """Index file from GCS to Elasticsearch"""
    basic_auth = (
        (elasticsearch_username, elasticsearch_password)
        if elasticsearch_username and elasticsearch_password
        else None
    )

    es_client = Elasticsearch(
        hosts=elasticsearch_hostname if elasticsearch_hostname else None,
        cloud_id=elasticsearch_cloud_id if elasticsearch_cloud_id else None,
        request_timeout=60,
        basic_auth=basic_auth,
    )

    file_manager = FileManager(gcs_path, gcp_project, "")

    indexer = Indexer(index_version, file_manager, es_client)
    indexer.index_from_export(total_docs, elasticsearch_alias)


@indexer_cmd.command()
def copy_export(
    export_base_url: str = job_settings.export_base_url,
    gcs_path: str = gcs_path_option,
    gcp_project: str = gcp_project_option,
):
    """Copy file from wikimedia to gcs"""
    file_manager = FileManager(gcs_path, gcp_project, export_base_url)

    logger.info(
        "Ensuring latest dump is on GCS",
        extra={"gcs_path": gcs_path, "gcp_project": gcp_project},
    )
    latest = file_manager.stream_latest_dump_to_gcs()
    if not latest.name:
        raise RuntimeError("Unable to ensure latest dump on GCS or missing file name.")
