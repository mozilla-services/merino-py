"""CLI commands for the csv_rs_uploader module"""

import asyncio
import csv
import importlib
import io

import typer

from merino.configs import settings as config
from merino.jobs.csv_rs_uploader.chunked_rs_uploader import (
    ChunkedRemoteSettingsSuggestionUploader,
)
from merino.jobs.utils.chunked_rs_uploader import ChunkedRemoteSettingsUploader

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
    "",
    "--collection",
    help="Remote settings collection ID",
)

keep_existing_records_option = typer.Option(
    False,
    "--keep-existing-records",
    help="Keep existing records not present in the new CSV data",
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
    "",
    "--csv-path",
    help="Path to CSV file containing the source data",
)

model_name_option = typer.Option(
    "",
    "--model-name",
    help="Name of the suggestion model module",
)

model_package_option = typer.Option(
    __name__,
    "--model-package",
    help="Name of the package containing the suggestion model module",
)

record_type_option = typer.Option(
    "",
    "--record-type",
    help="The `type` of each remote settings record [default: '{model_name}-suggestions']",
)

score_option = typer.Option(
    rs_settings.score,
    "--score",
    help="The score of each suggestion",
)

csv_rs_uploader_cmd = typer.Typer(
    name="csv-rs-uploader",
    help="Command for uploading suggestions from a CSV file to remote settings",
)


class MissingFieldError(Exception):
    """An error that means the input CSV did not contain an expected field."""

    pass


@csv_rs_uploader_cmd.command()
def upload(
    auth: str = auth_option,
    bucket: str = bucket_option,
    chunk_size: int = chunk_size_option,
    collection: str = collection_option,
    csv_path: str = csv_path_option,
    keep_existing_records: bool = keep_existing_records_option,
    dry_run: bool = dry_run_option,
    model_name: str = model_name_option,
    model_package: str = model_package_option,
    record_type: str = record_type_option,
    score: float = score_option,
    server: str = server_option,
):
    """Upload suggestions from a CSV file to remote settings."""
    if not csv_path:
        raise typer.BadParameter("--csv-path must be given")
    if not model_name:
        raise typer.BadParameter("--model-name must be given")

    asyncio.run(
        _upload(
            auth=auth,
            bucket=bucket,
            chunk_size=chunk_size,
            collection=collection,
            csv_path=csv_path,
            keep_existing_records=keep_existing_records,
            dry_run=dry_run,
            model_name=model_name,
            model_package=model_package,
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
    keep_existing_records: bool,
    dry_run: bool,
    model_name: str,
    model_package: str,
    record_type: str,
    score: float,
    server: str,
):
    with open(csv_path, newline="", encoding="utf-8-sig") as csv_file:
        await _upload_file_object(
            auth=auth,
            bucket=bucket,
            chunk_size=chunk_size,
            collection=collection,
            keep_existing_records=keep_existing_records,
            dry_run=dry_run,
            file_object=csv_file,
            model_name=model_name,
            model_package=model_package,
            record_type=record_type,
            score=score,
            server=server,
        )


async def _upload_file_object(
    auth: str,
    bucket: str,
    chunk_size: int,
    collection: str,
    file_object: io.TextIOWrapper,
    keep_existing_records: bool,
    dry_run: bool,
    model_name: str,
    model_package: str,
    record_type: str,
    score: float,
    server: str,
):
    if not record_type:
        record_type = f"{model_name}-suggestions"

    # Import the suggestion model module.
    try:
        model_module = importlib.import_module(f".{model_name}", package=model_package)
    except ModuleNotFoundError:
        raise ModuleNotFoundError(
            f"Suggestion model module `{model_name}` not found (relative to "
            f"package `{model_package}`)"
        )

    # Get the `Suggestion` class defined in the module.
    try:
        Suggestion = model_module.Suggestion
    except AttributeError:
        raise AttributeError(
            f"`Suggestion` class not found in suggestion model module "
            f"`{model_name}`. Please define a `Suggestion` class."
        )

    if not collection:
        collection = Suggestion.default_collection()
    csv_reader = csv.DictReader(file_object)

    # Generate the full list of suggestions before creating the chunked uploader
    # so we can validate the source data before deleting existing records and
    # starting the upload.
    suggestions = Suggestion.csv_to_suggestions(csv_reader)

    with ChunkedRemoteSettingsSuggestionUploader(
        auth=auth,
        bucket=bucket,
        chunk_size=chunk_size,
        collection=collection,
        dry_run=dry_run,
        record_type=record_type,
        server=server,
        suggestion_score_fallback=score,
        total_item_count=len(suggestions),
    ) as uploader:
        if not keep_existing_records:
            uploader.delete_records()

        for suggestion in suggestions:
            uploader.add_suggestion(suggestion.model_dump(mode="json"))
