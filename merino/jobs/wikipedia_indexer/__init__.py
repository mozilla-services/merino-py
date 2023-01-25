"""CLI commands for the wikipedia_indexer module"""
import logging
from typing import Optional

import click
from elasticsearch import Elasticsearch

from merino.jobs.wikipedia_indexer.filemanager import FileManager
from merino.jobs.wikipedia_indexer.indexer import Indexer

logger = logging.getLogger(__name__)

# Shared options
gcs_path_option = click.option(
    "--gcs-path",
    default="merino-jobs-dev/wikipedia-exports",
    type=str,
    help="Full gcs path to folder containing wikipedia exports on gcs",
)

gcp_project_option = click.option(
    "--gcp-project",
    default="contextual-services-dev",
    type=str,
    help="GCP project to use for gcs",
)


@click.group(help="Commands for indexing wikipedia exports into elasticsearch")
def indexer_cmd():
    """Create the click group for the wikipedia indexer subcommands"""
    pass


@indexer_cmd.command()
@click.option("--elasticsearch-hostname", default="http://35.192.164.92:9200/")
@click.option("--elasticsearch-username", default=None)
@click.option("--elasticsearch-password", default=None)
@click.option("--elasticsearch-alias", default="enwiki-{version}")
@click.option("--index-version", default="v1")
@click.option("--total-docs", default=6_400_000)
@gcp_project_option
@gcs_path_option
def index(
    elasticsearch_hostname: str,
    elasticsearch_alias: str,
    elasticsearch_username: Optional[str],
    elasticsearch_password: Optional[str],
    index_version: str,
    total_docs: int,
    gcs_path: str,
    gcp_project: str,
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
    file_manager = FileManager(gcs_path, gcp_project)

    indexer = Indexer(index_version, file_manager, es_client)
    indexer.index_from_export(total_docs, elasticsearch_alias)


@indexer_cmd.command()
@click.option(
    "--export-base-url",
    default="https://dumps.wikimedia.org/other/cirrussearch/current/",
)
@gcp_project_option
@gcs_path_option
def copy_export(export_base_url: str, gcs_path: str, gcp_project: str):
    """Copy file from wikimedia to gcs"""
    file_manager = FileManager(gcs_path, gcp_project, export_base_url)

    logger.info(
        "Ensuring latest dump is on GCS",
        extra={"gcs_path": gcs_path, "gcp_project": gcp_project},
    )
    latest = file_manager.stream_latest_dump_to_gcs()
    if not latest.name:
        raise RuntimeError("Unable to ensure latest dump on gcs or missing filename.")
