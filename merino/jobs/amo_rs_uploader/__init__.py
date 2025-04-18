"""CLI commands for the amo_rs_uploader module"""

import asyncio
import logging
from typing import Any

import typer

from merino.configs import settings as config
from merino.jobs.csv_rs_uploader import ChunkedRemoteSettingsSuggestionUploader
from merino.providers.suggest.amo.addons_data import ADDON_DATA, ADDON_KEYWORDS
from merino.providers.suggest.amo.backends.dynamic import DynamicAmoBackend

logger = logging.getLogger(__name__)

amo_settings = config.providers.amo
job_settings = config.jobs.amo_rs_uploader
rs_settings = config.remote_settings

# Options
auth_option = typer.Option(
    rs_settings.auth,
    "--auth",
    help="Remote settings authorization token",
)

bucket_option = typer.Option(
    rs_settings.bucket,
    "--bucket",
    help="Remote settings bucket",
)

chunk_size_option = typer.Option(
    rs_settings.chunk_size,
    "--chunk-size",
    help="The number of suggestions to store in each attachment",
)

collection_option = typer.Option(
    rs_settings.collection,
    "--collection",
    help="Remote settings collection ID",
)

keep_existing_records_option = typer.Option(
    False,
    "--keep-existing-records",
    help="Keep existing records before uploading new records",
)

dry_run_option = typer.Option(
    rs_settings.dry_run,
    "--dry-run",
    help="Log the records that would be uploaded but don't upload them",
)

server_option = typer.Option(
    rs_settings.server,
    "--server",
    help="Remote settings server",
)

record_type_option = typer.Option(
    job_settings.record_type,
    "--record-type",
    help="The `type` of each remote settings record",
)

score_option = typer.Option(
    amo_settings.score,
    "--score",
    help="The score of each suggestion",
)

amo_rs_uploader_cmd = typer.Typer(
    name="amo-rs-uploader",
    help="Command for uploading AMO add-on suggestions to remote settings",
)


@amo_rs_uploader_cmd.command()
def upload(
    auth: str = auth_option,
    bucket: str = bucket_option,
    chunk_size: int = chunk_size_option,
    collection: str = collection_option,
    keep_existing_records: bool = keep_existing_records_option,
    dry_run: bool = dry_run_option,
    record_type: str = record_type_option,
    score: float = score_option,
    server: str = server_option,
):
    """Upload AMO suggestions to remote settings."""
    asyncio.run(
        _upload(
            auth=auth,
            bucket=bucket,
            chunk_size=chunk_size,
            collection=collection,
            keep_existing_records=keep_existing_records,
            dry_run=dry_run,
            record_type=record_type,
            score=score,
            server=server,
        )
    )


async def _upload(
    auth: str,
    bucket: str,
    chunk_size: int,
    collection: str,
    keep_existing_records: bool,
    dry_run: bool,
    record_type: str,
    score: float,
    server: str,
):
    logger.info("Fetching addons data from AMO")
    backend = DynamicAmoBackend(config.amo.dynamic.api_url)
    await backend.fetch_and_cache_addons_info()

    with ChunkedRemoteSettingsSuggestionUploader(
        auth=auth,
        bucket=bucket,
        chunk_size=chunk_size,
        collection=collection,
        dry_run=dry_run,
        record_type=record_type,
        server=server,
        suggestion_score_fallback=score,
        total_item_count=len(backend.dynamic_data),
    ) as uploader:
        if not keep_existing_records:
            uploader.delete_records()

        for addon, dynamic_data in backend.dynamic_data.items():
            # Merge static and dynamic addon data.
            suggestion: dict[str, Any] = ADDON_DATA[addon] | dynamic_data

            # Use "title" instead of "name" to be consistent with Merino's
            # `AddonSuggestion` schema.
            suggestion["title"] = suggestion["name"]
            del suggestion["name"]

            # Add keywords. Sort them to make it easier to compare keywords from
            # one dataset to the next.
            suggestion["keywords"] = sorted([kw.lower() for kw in ADDON_KEYWORDS[addon]])

            uploader.add_suggestion(suggestion)
