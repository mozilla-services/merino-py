"""CLI commands for the wiki_rs_uploader module"""

import asyncio
from typing import Any

import typer

from merino.configs import settings as config
from merino.jobs.csv_rs_uploader.chunked_rs_uploader import (
    ChunkedRemoteSettingsSuggestionUploader,
)
from merino.jobs.utils.chunked_rs_uploader import Chunk
from merino.jobs.wikipedia_offline_uploader.downloader import get_wiki_suggestions
from merino.jobs.utils.rs_client import filter_expression_dict, logger

rs_settings = config.remote_settings

# Options
auth_option = typer.Option(
    rs_settings.auth,
    "--auth",
    help="Remote settings authorization token",
)

bucket_option = typer.Option(
    "main-workspace",
    "--bucket",
    help="Remote settings bucket",
)

chunk_size_option = typer.Option(
    rs_settings.chunk_size,
    "--chunk-size",
    help="The number of suggestions to store in each attachment",
)

collection_option = typer.Option(
    "quicksuggest-other",
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

score_option = typer.Option(
    rs_settings.score,
    "--score",
    help="The score of each suggestion",
)

language_option = typer.Option(
    "en",
    "--languages",
    help="The language to retrieve suggestions for",
)

days_option = typer.Option(
    "90",
    "--days",
    help="The number of days to retrieve suggestions for",
)

relevance_type_option = typer.Option(
    "frequency",
    "--relevance-type",
    help="Retrieve suggestion based on recency or frequency",
)

access_type_option = typer.Option(
    "all-access",
    "--access-type",
    help="Access type should be one of 'all-access', 'desktop', 'mobile-app', and 'mobile-web'",
)

wiki_offline_uploader_cmd = typer.Typer(
    name="wiki-offline-uploader",
    help="Command for uploading wiki suggestions",
)

LOCALES_MAPPING = {
    "en": ["en-US", "en-CA", "en-GB"],
    "fr": ["fr", "fr-FR"],
    "de": ["de", "de-DE"],
    "it": ["it", "it-IT"],
    "pl": ["pl", "pl-PL"],
}


class MissingFieldError(Exception):
    """An error that means the input CSV did not contain an expected field."""

    pass


@wiki_offline_uploader_cmd.command()
def upload(
    auth: str = auth_option,
    bucket: str = bucket_option,
    chunk_size: int = chunk_size_option,
    collection: str = collection_option,
    keep_existing_records: bool = keep_existing_records_option,
    dry_run: bool = dry_run_option,
    score: float = score_option,
    server: str = server_option,
    languages: str = language_option if language_option else "en",
    relevance_type: str = relevance_type_option if relevance_type_option else "frequency",
    access_type: str = access_type_option if access_type_option else "all-access",
    days: int = days_option,
):
    """Upload wikipedia suggestions to remote settings."""
    asyncio.run(
        _upload(
            auth=auth,
            bucket=bucket,
            chunk_size=chunk_size,
            collection=collection,
            keep_existing_records=keep_existing_records,
            dry_run=dry_run,
            score=score,
            server=server,
            languages=languages,
            relevance_type=relevance_type,
            access_type=access_type,
            days=days,
        )
    )


async def _upload(
    auth: str,
    bucket: str,
    chunk_size: int,
    collection: str,
    keep_existing_records: bool,
    dry_run: bool,
    score: float,
    server: str,
    languages: str,
    relevance_type: str,
    access_type: str,
    days: int,
):
    await _upload_file_object(
        auth=auth,
        bucket=bucket,
        chunk_size=chunk_size,
        collection=collection,
        keep_existing_records=keep_existing_records,
        dry_run=dry_run,
        score=score,
        server=server,
        languages=languages,
        relevance_type=relevance_type,
        access_type=access_type,
        days=days,
    )


async def _upload_file_object(
    auth: str,
    bucket: str,
    chunk_size: int,
    collection: str,
    keep_existing_records: bool,
    dry_run: bool,
    score: float,
    server: str,
    languages: str,
    relevance_type: str,
    access_type: str,
    days: int,
):
    record_type = "wikipedia"

    result = await get_wiki_suggestions(languages, relevance_type, access_type, days)
    for language, suggestions in result.items():
        with WikipediaSuggestionChunkRemoteSettingsUploader(
            auth=auth,
            bucket=bucket,
            chunk_size=chunk_size,
            collection=collection,
            dry_run=dry_run,
            record_type=record_type,
            server=server,
            suggestion_score_fallback=score,
            total_item_count=len(suggestions),
            language=language,
        ) as uploader:
            if not keep_existing_records:
                uploader.delete_records()

            for suggestion in suggestions:
                uploader.add_suggestion(suggestion)


class WikipediaChunk(Chunk):
    """A chunk of items for the wikipedia uploader."""

    uploader: "WikipediaSuggestionChunkRemoteSettingsUploader"

    def to_record(self) -> dict[str, Any]:
        """Create the record for the chunk."""
        start, end = self.pretty_indexes()
        record_id = "-".join(
            ["data", self.uploader.record_type, self.uploader.language, start, end]
        )
        filter_expression = filter_expression_dict(
            locales=LOCALES_MAPPING.get(self.uploader.language, [])
        )
        return {
            "id": record_id,
            "type": self.uploader.record_type,
            **filter_expression,
        }


class WikipediaSuggestionChunkRemoteSettingsUploader(ChunkedRemoteSettingsSuggestionUploader):
    """A class that uploads wikipedia suggestions to remote settings."""

    def __init__(
        self,
        auth: str,
        bucket: str,
        chunk_size: int,
        collection: str,
        record_type: str,
        server: str,
        language: str,
        dry_run: bool = False,
        total_item_count: int | None = None,
        suggestion_score_fallback: float | None = None,
    ):
        super().__init__(
            auth,
            bucket,
            chunk_size,
            collection,
            record_type,
            server,
            dry_run,
            suggestion_score_fallback,
            total_item_count,
            chunk_cls=WikipediaChunk,
        )
        self.language = language

    def delete_records(self) -> None:
        """Delete records of the same language and id."""
        logger.info(f"Deleting records with type: {self.record_type}")
        for record in self.client.get_records():
            if record.get("type") == self.record_type and self.language in record["id"]:
                self.client.delete_record(record["id"])
