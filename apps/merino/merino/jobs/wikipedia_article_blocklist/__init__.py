"""CLI commands for the wikipedia_article_blocklist module"""

import logging
from datetime import datetime

import typer

from merino.configs import settings as config
from merino.jobs.wikipedia_article_blocklist.generator import ArticleBlocklistGenerator
from merino.jobs.wikipedia_article_blocklist.utils import create_blocklist
from merino.jobs.wikipedia_indexer.filemanager import FileManager
from merino.utils.gcs import initialize_storage_client

logger = logging.getLogger(__name__)

job_settings = config.jobs.wikipedia_article_blocklist
indexer_settings = config.jobs.wikipedia_indexer

# The article blocklist is only generated from the English export.
LANGUAGE = "en"

DESTINATION_PREFIX = "suggest-merino-exports/wikipedia/article_blocklist"

article_blocklist_cmd = typer.Typer(
    name="wikipedia-article-blocklist",
    help="Commands for generating the Wikipedia article blocklist",
)


@article_blocklist_cmd.command()
def generate(
    blocklist_file_url: str = indexer_settings.blocklist_file_url,
    total_docs: int = indexer_settings.total_docs,
    gcs_path: str = typer.Option(
        indexer_settings.gcs_path,
        "--gcs-path",
        help="Full GCS path to the folder containing Wikipedia exports",
    ),
    gcp_project: str = typer.Option(
        indexer_settings.gcp_project,
        "--gcp-project",
        help="GCP project to use for reading the Wikipedia exports",
    ),
    gcs_storage_bucket: str = typer.Option(
        job_settings.gcs_storage_bucket,
        "--gcs-storage-bucket",
        help="GCS bucket to write the article blocklist CSV to",
    ),
    gcs_storage_project: str = typer.Option(
        job_settings.gcs_storage_project,
        "--gcs-storage-project",
        help="GCP project of the GCS bucket to write the article blocklist CSV to",
    ),
):
    """Write the title and QID of English articles in a blocked category to a CSV on GCS"""
    # check the destination up front
    if not gcs_storage_bucket or not gcs_storage_project:
        raise ValueError("Both the GCS storage bucket and project must be set")

    blocklist = create_blocklist(blocklist_file_url)

    logger.info("Starting Wikipedia article blocklist generation")

    file_manager = FileManager(gcs_path, gcp_project, "", LANGUAGE)
    content = ArticleBlocklistGenerator(blocklist, file_manager).generate(total_docs)

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")

    client = initialize_storage_client(destination_gcp_project=gcs_storage_project)
    bucket = client.bucket(gcs_storage_bucket)
    blob = bucket.blob(f"{DESTINATION_PREFIX}/{timestamp}.csv")
    blob.upload_from_string(content, content_type="text/csv")
    bucket.copy_blob(blob, bucket, f"{DESTINATION_PREFIX}/latest.csv")

    logger.info("Uploaded Wikipedia article blocklist", extra={"blob": blob.name})
