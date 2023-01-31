"""CLI commands for the wikipedia_indexer module"""
import logging
from typing import Optional

import typer
from elasticsearch import Elasticsearch

from merino.jobs.wikipedia_indexer.filemanager import FileManager
from merino.jobs.wikipedia_indexer.indexer import Indexer

logger = logging.getLogger(__name__)

# Shared options
gcs_path_option = typer.Option(
    "merino-jobs-dev/wikipedia-exports",
    "--gcs-path",
    help="Full gcs path to folder containing wikipedia exports on gcs",
)

gcp_project_option = typer.Option(
    "contextual-services-dev",
    "--gcp-project",
    help="GCP project to use for gcs",
)

indexer_cmd = typer.Typer(
    name="wikipedia-indexer",
    help="Commands for indexing wikipedia exports into elasticsearch",
)


@indexer_cmd.command()
def index(
    elasticsearch_hostname: str = "http://35.192.164.92:9200/",
    elasticsearch_alias: str = "enwiki",
    elasticsearch_username: Optional[str] = None,
    elasticsearch_password: Optional[str] = None,
    index_version: str = "v1",
    total_docs: int = 6_400_00,
    gcs_path: str = gcs_path_option,
    gcp_project: str = gcp_project_option,
):
    """Index file from gcs to elasticsearch"""
    basic_auth = (
        (elasticsearch_username, elasticsearch_password)
        if elasticsearch_username and elasticsearch_password
        else None
    )
    es_client = Elasticsearch(
        hosts=[elasticsearch_hostname], request_timeout=60, basic_auth=basic_auth
    )
    file_manager = FileManager(gcs_path, gcp_project, "")

    indexer = Indexer(index_version, file_manager, es_client)
    indexer.index_from_export(total_docs, elasticsearch_alias)


@indexer_cmd.command()
def copy_export(
    export_base_url: str = "https://dumps.wikimedia.org/other/cirrussearch/current/",
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
        raise RuntimeError("Unable to ensure latest dump on gcs or missing filename.")
