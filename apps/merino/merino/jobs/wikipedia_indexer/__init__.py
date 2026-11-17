"""CLI commands for the wikipedia_indexer module"""

import asyncio
import logging
from enum import StrEnum
from typing import Annotated

import typer

from merino.configs import settings as config
from merino.jobs.wikipedia_indexer.filemanager import FileManager
from merino.jobs.wikipedia_indexer.indexer import Indexer
from merino.jobs.wikipedia_indexer.utils import (
    BLOCKED_TITLES_DIR,
    load_article_blocklist,
    upload_blocked_titles,
)
from merino.search.elastic import ElasticSearchAdapter
from merino.utils.blocklists import WIKIPEDIA_TITLE_BLOCKLIST

logger = logging.getLogger(__name__)

job_settings = config.jobs.wikipedia_indexer
# The article blocklist job writes the blocklist the indexer reads, so both share its location.
article_blocklist_settings = config.jobs.wikipedia_article_blocklist


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


class RunMode(StrEnum):
    """What a run of the `index` command produces."""

    # Scan the export for articles in the article blocklist and upload their titles.
    BLOCKLIST_ONLY = "blocklist-only"
    # Build and publish the index, without uploading the blocked titles.
    INDEX_ONLY = "index-only"
    # Build and publish the index, then upload the titles it blocked.
    BOTH = "both"


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
    elasticsearch_request_timeout: float = job_settings.es_request_timeout,
    elasticsearch_create_index_timeout: float = job_settings.es_create_index_timeout,
    follower_sync_timeout: float = job_settings.follower_sync_timeout,
    follower_sync_poll_interval: float = job_settings.follower_sync_poll_interval,
    follower_discovery_period: float = job_settings.follower_discovery_period,
    article_blocklist_bucket: str = typer.Option(
        article_blocklist_settings.gcs_storage_bucket,
        "--article-blocklist-bucket",
        help="GCS bucket holding the article blocklist CSV",
    ),
    article_blocklist_prefix: str = typer.Option(
        article_blocklist_settings.destination_prefix,
        "--article-blocklist-prefix",
        help="Object prefix (folders) in the GCS bucket holding the article blocklist CSV",
    ),
    article_blocklist_project: str = typer.Option(
        article_blocklist_settings.gcs_storage_project,
        "--article-blocklist-project",
        help="GCP project of the GCS bucket holding the article blocklist CSV",
    ),
    blocked_titles_destination: str = typer.Option(
        job_settings.blocked_titles_destination,
        "--blocked-titles-destination",
        help="Object prefix (folders) where each run uploads the titles it blocked",
    ),
    index_version: str = version_option,
    total_docs: int = job_settings.total_docs,
    gcs_path: str = gcs_path_option,
    gcp_project: str = gcp_project_option,
    mode: RunMode = typer.Option(
        RunMode.BOTH,
        "--mode",
        help=(
            "What to produce: `index-only` builds and publishes the index, `blocklist-only` "
            "uploads the titles of the articles in the article blocklist without indexing, "
            "`both` does both"
        ),
    ),
):
    """Index file from GCS to Elasticsearch and/or upload the blocked titles"""
    if not all((article_blocklist_bucket, article_blocklist_prefix, article_blocklist_project)):
        raise ValueError("Article blocklist GCS values must be set")

    elasticsearch = ElasticSearchAdapter(
        url=elasticsearch_url,
        api_key=elasticsearch_api_key,
        request_timeout=elasticsearch_request_timeout,
        create_index_timeout=elasticsearch_create_index_timeout,
    )

    article_blocklist = load_article_blocklist(
        article_blocklist_bucket, article_blocklist_prefix, article_blocklist_project
    )

    logger.info(f"Starting Wikipedia indexing for language: {language}")

    file_manager = FileManager(gcs_path, gcp_project, "", language)

    alias_key = f"{language}_es_alias"
    elasticsearch_alias = job_settings[alias_key]

    indexer = Indexer(
        index_version,
        article_blocklist,
        WIKIPEDIA_TITLE_BLOCKLIST,
        file_manager,
        elasticsearch,
        follower_sync_timeout=follower_sync_timeout,
        follower_sync_poll_interval=follower_sync_poll_interval,
        follower_discovery_period=follower_discovery_period,
    )
    if mode is RunMode.BLOCKLIST_ONLY:
        indexer.collect_blocked_titles(total_docs)
    else:
        indexer.index_from_export(total_docs, elasticsearch_alias)

    if mode is RunMode.INDEX_ONLY:
        return

    # upload blocklist titles, next to the article blocklist
    destination = (
        blocked_titles_destination or f"{article_blocklist_prefix.strip('/')}/{BLOCKED_TITLES_DIR}"
    )
    try:
        blob_name = upload_blocked_titles(
            indexer.blocked_titles,
            article_blocklist_bucket,
            destination,
            article_blocklist_project,
            language,
        )
    except Exception:
        if mode is RunMode.BLOCKLIST_ONLY:
            # Uploading is all this mode does, so a failure must fail the job.
            raise
        logger.exception(
            "Failed to upload blocked titles",
            extra={
                "bucket": article_blocklist_bucket,
                "destination": destination,
                "blocked_titles": len(indexer.blocked_titles),
            },
        )
    else:
        logger.info(
            "Uploaded blocked titles",
            extra={"blob": blob_name, "blocked_titles": len(indexer.blocked_titles)},
        )


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
    latest = asyncio.run(file_manager.stream_latest_dump_to_gcs())
    if latest is None:
        raise RuntimeError(
            f"No complete {language} CirrusSearch export found under {export_base_url}."
        )
