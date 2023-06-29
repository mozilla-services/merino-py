"""CLI commands for the pocket_rs_uploader module"""
import asyncio
import csv
import io
from typing import Any

import typer
from pydantic import BaseModel, HttpUrl, validator

from merino.config import settings as config
from merino.jobs.utils.chunked_rs_uploader import ChunkedRemoteSettingsUploader

# The names of expected fields (columns) in the CSV input data.
FIELD_DESC = "Collection Description"
FIELD_KEYWORDS_LOW = "Low-Confidence Keywords"
FIELD_KEYWORDS_HIGH = "High-Confidence Keywords"
FIELD_TITLE = "Collection Title"
FIELD_URL = "Collection URL"

ALL_FIELDS = [
    FIELD_DESC,
    FIELD_KEYWORDS_LOW,
    FIELD_KEYWORDS_HIGH,
    FIELD_TITLE,
    FIELD_URL,
]

# The names of fields whose values are suggestion keywords. In the input data,
# the values of these fields are expected to be comma-delimited strings. The
# uploader converts them to arrays in the output JSON.
KEYWORDS_FIELDS = [
    FIELD_KEYWORDS_LOW,
    FIELD_KEYWORDS_HIGH,
]

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


class Suggestion(BaseModel):
    """Model for Pocket suggestions as encoded in the output JSON."""

    url: HttpUrl
    title: str
    description: str
    lowConfidenceKeywords: list[str]
    highConfidenceKeywords: list[str]

    def _validate_str(cls, value: str, name: str) -> str:
        if not value:
            raise ValueError(f"{name} must not be empty")
        return value

    def _validate_keywords(cls, value: list[str], name: str) -> list[str]:
        if not value or len(value) == 0:
            raise ValueError(f"{name} must not be empty")
        if any(map(lambda kw: not kw, value)):
            raise ValueError(f"{name} must not contain any empty strings")
        if any(map(lambda kw: kw.strip() != kw, value)):
            raise ValueError(f"{name} must not contain leading or trailing spaces")
        if any(map(lambda kw: kw.lower() != kw, value)):
            raise ValueError(f"{name} must not contain uppercase chars")
        return value

    @validator("title", pre=True, always=True)
    def validate_title(cls, value):
        """Validate title"""
        return cls._validate_str(cls, value, "title")

    @validator("description", pre=True, always=True)
    def validate_description(cls, value):
        """Validate description"""
        return cls._validate_str(cls, value, "description")

    @validator("lowConfidenceKeywords", pre=True, always=True)
    def validate_lowConfidenceKeywords(cls, value):
        """Validate lowConfidenceKeywords"""
        return cls._validate_keywords(cls, value, "lowConfidenceKeywords")

    @validator("highConfidenceKeywords", pre=True, always=True)
    def validate_highConfidenceKeywords(cls, value):
        """Validate highConfidenceKeywords"""
        return cls._validate_keywords(cls, value, "highConfidenceKeywords")


class MissingFieldError(Exception):
    """An error that means the input CSV did not contain an expected field."""

    pass


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
        await _upload_file_object(
            auth=auth,
            bucket=bucket,
            chunk_size=chunk_size,
            collection=collection,
            delete_existing_records=delete_existing_records,
            dry_run=dry_run,
            file_object=csv_file,
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
    delete_existing_records: bool,
    dry_run: bool,
    record_type: str,
    score: float,
    server: str,
):
    csv_reader = csv.DictReader(file_object)

    # Generate the full list of suggestions before creating the chunked uploader
    # so we can validate the source data before deleting existing records and
    # starting the upload.
    suggestions: list[Suggestion] = []
    for row in csv_reader:
        for field in ALL_FIELDS:
            if field not in row:
                raise MissingFieldError(f"Missing field {field}")

        # The keywords fields are comma-delimited strings. Split them into lists
        # and transform each individual keyword string as follows:
        # - Lowercase
        # - Remove leading and trailing space
        # - Filter out empty keywords
        keywords = {}
        for field in KEYWORDS_FIELDS:
            keywords[field] = [
                *filter(
                    lambda kw: len(kw) > 0,
                    map(str.strip, row[field].lower().split(",")),
                )
            ]

        suggestions.append(
            Suggestion(
                url=row[FIELD_URL],
                title=row[FIELD_TITLE],
                description=row[FIELD_DESC],
                lowConfidenceKeywords=keywords[FIELD_KEYWORDS_LOW],
                highConfidenceKeywords=keywords[FIELD_KEYWORDS_HIGH],
            )
        )

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
            uploader.add_suggestion(vars(suggestion))
