"""CLI commands for the wiki_rs_uploader module"""

import asyncio
import logging
from typing import Any

import typer

from merino.configs import settings as config
from merino.jobs.utils.rs_client import RemoteSettingsClient, filter_expression_dict
from merino.jobs.wikipedia_offline_uploader.downloader import get_wiki_suggestions

rs_settings = config.remote_settings
logger = logging.getLogger(__name__)
RECORD_TYPE = "wikipedia"

LOCALES_MAPPING = {
    "en": ["en-US", "en-CA", "en-GB"],
    "fr": ["fr", "fr-FR"],
    "de": ["de", "de-DE"],
    "it": ["it", "it-IT"],
    "pl": ["pl", "pl-PL"],
}

DEFAULT_LANGUAGES = ",".join(LOCALES_MAPPING.keys())

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
    DEFAULT_LANGUAGES,
    "--languages",
    help=(
        "Comma-separated languages to retrieve suggestions for. "
        f"Defaults to all supported languages ({DEFAULT_LANGUAGES})."
    ),
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


class MissingFieldError(Exception):
    """An error that means the input CSV did not contain an expected field."""

    pass


@wiki_offline_uploader_cmd.command()
def upload(
    auth: str = auth_option,
    bucket: str = bucket_option,
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
    rs_client = RemoteSettingsClient(
        auth=auth,
        bucket=bucket,
        collection=collection,
        server=server,
        dry_run=dry_run,
    )

    result = await get_wiki_suggestions(languages, relevance_type, access_type, days, score)

    for language, suggestions in result.items():
        if not keep_existing_records:
            _delete_records_for_language(rs_client, language)

        rs_client.upload(record=_build_record(language), attachment=suggestions)


def _build_record(language: str) -> dict[str, Any]:
    """Build the remote settings record for a language."""
    return {
        "id": f"data-{RECORD_TYPE}-{language}",
        "type": RECORD_TYPE,
        **filter_expression_dict(locales=LOCALES_MAPPING.get(language, [])),
    }


def _delete_records_for_language(rs_client: RemoteSettingsClient, language: str) -> None:
    """Delete existing wikipedia records for the given language."""
    logger.info(f"Deleting records with type: {RECORD_TYPE} for language: {language}")
    if rs_client.dry_run:  # pragma: no cover
        return
    prefix = f"data-{RECORD_TYPE}-{language}"
    for record in rs_client.get_records():
        # delete based on prefix to handle older chunked records
        if record.get("type") == RECORD_TYPE and (
            record["id"] == prefix or record["id"].startswith(f"{prefix}-")
        ):
            rs_client.delete_record(record["id"])
