"""CLI commands for the pocket_rs_uploader module"""
import asyncio
import csv
from typing import Any

import typer

from merino.config import settings as config
from merino.jobs.utils.chunked_rs_uploader import ChunkedRemoteSettingsUploader

# Maps from CSV field name in the input data to the corresponding suggestion
# property in the output.
SUGGESTION_PROPERTIES_BY_CSV_FIELD = {
    "Collection Title": "title",
    "Collection Description": "description",
    "Collection URL": "url",
    "High-Confidence Keywords": "highConfidenceKeywords",
    "Low-Confidence Keywords": "lowConfidenceKeywords",
}

job_settings = config.jobs.pocket_rs_uploader
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

delete_existing_records_option = typer.Option(
    rs_settings.delete_existing_records,
    "--delete-existing-records",
    help="Delete existing records before uploading new records",
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

csv_path_option = typer.Option(
    job_settings.csv_path,
    "--csv-path",
    help="Path to CSV file containing the source data",
)

record_type_option = typer.Option(
    job_settings.record_type,
    "--record-type",
    help="The `type` of each remote settings record",
)

score_option = typer.Option(
    job_settings.score,
    "--score",
    help="The score of each suggestion",
)

pocket_rs_uploader_cmd = typer.Typer(
    name="pocket-rs-uploader",
    help="Command for uploading Pocket suggestions to remote settings",
)


@pocket_rs_uploader_cmd.command()
def upload(
    auth: str = auth_option,
    bucket: str = bucket_option,
    chunk_size: int = chunk_size_option,
    collection: str = collection_option,
    csv_path: str = csv_path_option,
    delete_existing_records: bool = delete_existing_records_option,
    dry_run: bool = dry_run_option,
    record_type: str = record_type_option,
    score: float = score_option,
    server: str = server_option,
):
    """Upload Pocket suggestions to remote settings."""
    asyncio.run(
        _upload(
            auth=auth,
            bucket=bucket,
            chunk_size=chunk_size,
            collection=collection,
            csv_path=csv_path,
            delete_existing_records=delete_existing_records,
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
    csv_path: str,
    delete_existing_records: bool,
    dry_run: bool,
    record_type: str,
    score: float,
    server: str,
):
    with open(csv_path, newline="", encoding="utf-8-sig") as csv_file:
        csv_reader = csv.DictReader(csv_file)

        # Generate the full list of suggestions before creating the chunked
        # uploader so we can detect errors in the source data before deleting
        # existing records and starting the upload.
        suggestions: list[dict[str, Any]] = []
        for row in csv_reader:
            suggestion: dict[str, Any] = {}
            for field, prop in SUGGESTION_PROPERTIES_BY_CSV_FIELD.items():
                if not row[field]:
                    raise Exception(f"Empty value for '{field}' in row: {row}")
                suggestion[prop] = row[field]

            # The two keywords fields are comma-delimited strings. Split them
            # into arrays.
            for prop in ["highConfidenceKeywords", "lowConfidenceKeywords"]:
                suggestion[prop] = [
                    *map(str.strip, suggestion[prop].lower().split(","))
                ]

            suggestions.append(suggestion)

        with ChunkedRemoteSettingsUploader(
            auth=auth,
            bucket=bucket,
            chunk_size=chunk_size,
            collection=collection,
            dry_run=dry_run,
            record_type=record_type,
            server=server,
            suggestion_score_fallback=score,
            total_suggestion_count=len(suggestions),
        ) as uploader:
            if delete_existing_records:
                uploader.delete_records()

            for suggestion in suggestions:
                uploader.add_suggestion(suggestion)
