"""CLI commands for the relevancy_csv_rs_uploader module"""

import asyncio
import base64
import csv
import io
from collections import defaultdict
from enum import Enum
from hashlib import md5

import typer
from pydantic import BaseModel

from merino.config import settings as config
from merino.jobs.relevancy_uploader.chunked_rs_uploader import (
    ChunkedRemoteSettingsRelevancyUploader,
)

CLASSIFICATION_CURRENT_VERSION = 1


class Category(Enum):
    """Enum of possible interests for a domain."""

    Inconclusive = 0
    Animals = 1
    Arts = 2
    Autos = 3
    Business = 4
    Career = 5
    Education = 6
    Fashion = 7
    Finance = 8
    Food = 9
    Government = 10
    # Disable this per policy consultation
    # Health = 11
    Hobbies = 12
    Home = 13
    News = 14
    RealEstate = 15
    Society = 16
    Sports = 17
    Tech = 18
    Travel = 19


RELEVANCY_RECORD_TYPE = "category_to_domains"

# Mapping to unify categories across the sources
UPLOAD_CATEGORY_TO_R2D2_CATEGORY: dict[str, Category] = {
    "Sports": Category.Sports,
    "Economy & Finance": Category.Finance,
    "Ecommerce": Category.Inconclusive,
    "Travel": Category.Travel,
    "Information Technology": Category.Tech,
    "News & Media": Category.News,
    "Chat": Category.Inconclusive,
    "Photography": Category.Hobbies,
    "Social Networks": Category.Inconclusive,
    "Instant Messengers": Category.Inconclusive,
    "Business": Category.Business,
    "Health & Fitness": Category.Inconclusive,
    "Music": Category.Hobbies,
    "Home & Garden": Category.Home,
    "Science": Category.Education,
    "Fashion": Category.Fashion,
    "Technology": Category.Tech,
    "Food & Drink": Category.Food,
    "Video Streaming": Category.Hobbies,
    "Education": Category.Education,
    "Lifestyle": Category.Inconclusive,
    "Cartoons & Anime": Category.Inconclusive,
    "Gaming": Category.Hobbies,
    "Magazines": Category.Inconclusive,
    "Forums": Category.Inconclusive,
    "Entertainment": Category.Inconclusive,
    "Clothing": Category.Fashion,
    "Weather": Category.Inconclusive,
    "Government": Category.Government,
}


class RelevancyData:
    """Class to relate to conforming data to remote settings structure."""

    @classmethod
    def csv_to_relevancy_data(cls, csv_reader) -> defaultdict[Category, list[dict[str, str]]]:
        """Read CSV file and extract required data for relevancy in the structure
        [
            { "domain" : <base64 string> }
        ]
        """
        rows = sorted(csv_reader, key=lambda x: x["categories"])
        data: defaultdict[Category, list[dict[str, str]]] = defaultdict(list)
        for row in rows:
            categories = row["categories"].strip("[]").split(",")
            for category in categories:
                category_mapped = UPLOAD_CATEGORY_TO_R2D2_CATEGORY.get(
                    category, Category.Inconclusive
                )
                md5_hash = md5(row["domain"].encode(), usedforsecurity=False).digest()
                data[category_mapped].append({"domain": base64.b64encode(md5_hash).decode()})
        return data


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
    "content-relevance",
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

csv_path_option = typer.Option(
    "",
    "--csv-path",
    help="Path to CSV file containing the source data",
)

version_option = typer.Option(
    CLASSIFICATION_CURRENT_VERSION,
    "--version",
    help="version of the classification data",
)


relevancy_csv_rs_uploader_cmd = typer.Typer(
    name="relevancy-csv-rs-uploader",
    help="Command for uploading domain data from a CSV file to remote settings",
)


class MissingFieldError(Exception):
    """An error that means the input CSV did not contain an expected field."""

    pass


@relevancy_csv_rs_uploader_cmd.command()
def upload(
    auth: str = auth_option,
    bucket: str = bucket_option,
    chunk_size: int = chunk_size_option,
    collection: str = collection_option,
    csv_path: str = csv_path_option,
    keep_existing_records: bool = keep_existing_records_option,
    dry_run: bool = dry_run_option,
    server: str = server_option,
    version: int = version_option,
):
    """Upload relevancy domains from a CSV file to remote settings."""
    if not csv_path:
        raise typer.BadParameter("--csv-path must be given")

    asyncio.run(
        _upload(
            auth=auth,
            bucket=bucket,
            chunk_size=chunk_size,
            collection=collection,
            csv_path=csv_path,
            keep_existing_records=keep_existing_records,
            dry_run=dry_run,
            server=server,
            version=version,
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
    server: str,
    version: int,
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
            server=server,
            version=version,
        )


async def _upload_file_object(
    auth: str,
    bucket: str,
    chunk_size: int,
    collection: str,
    file_object: io.TextIOWrapper,
    keep_existing_records: bool,
    dry_run: bool,
    server: str,
    version: int,
):
    csv_reader = csv.DictReader(file_object)

    # Generate the full list of domains before creating the chunked uploader
    # so we can validate the source data before deleting existing records and
    # starting the upload.
    data = RelevancyData.csv_to_relevancy_data(csv_reader)

    # since we upload based on category not record type,
    # we need to delete records before iterating on categories
    # or else we either delete the entire collection after each
    # category upload or delete a category at a time, which may not
    # cover all categories.
    with ChunkedRemoteSettingsRelevancyUploader(
        auth=auth,
        bucket=bucket,
        chunk_size=chunk_size,
        collection=collection,
        dry_run=dry_run,
        record_type=RELEVANCY_RECORD_TYPE,
        server=server,
        category_name="",
        category_code=0,
        version=version,
    ) as uploader:
        if not keep_existing_records:
            uploader.delete_records()

    for category, domains in data.items():
        with ChunkedRemoteSettingsRelevancyUploader(
            auth=auth,
            bucket=bucket,
            chunk_size=chunk_size,
            collection=collection,
            dry_run=dry_run,
            record_type=RELEVANCY_RECORD_TYPE,
            server=server,
            total_data_count=len(data[category]),
            category_name=category.name,
            category_code=category.value,
            version=version,
        ) as uploader:
            for domain in domains:
                uploader.add_data(domain)
