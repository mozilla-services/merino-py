"""CLI commands for the relevancy_csv_rs_uploader module"""
import asyncio
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


class Category(Enum):
    """Enum of possible interests for a domain."""

    Animals = 0
    Arts = 1
    Autos = 2
    Business = 3
    Career = 4
    Education = 5
    Fashion = 6
    Finance = 7
    Food = 8
    Government = 9
    Health = 10
    Hobbies = 11
    Home = 12
    News = 13
    RealEstate = 14
    Society = 15
    Sports = 16
    Tech = 17
    Travel = 18
    Inconclusive = 19


RELEVANCY_RECORD_TYPE = "category_to_domains"

# Mapping to unify categories across the sources
MAPPING: dict[str, Category] = {
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
    "Health & Fitness": Category.Health,
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


class RelevancyData(BaseModel):
    """Pydantic base model for remote settings relevancy data."""

    @classmethod
    def csv_to_relevancy_data(
        cls, csv_reader
    ) -> defaultdict[Category, list[dict[str, str]]]:
        """Read CSV file and extract required data for relevancy."""
        rows = sorted(csv_reader, key=lambda x: x["categories"])
        data: defaultdict[Category, list[dict[str, str]]] = defaultdict(list)
        for row in rows:
            categories = row["categories"].strip("[]").split(",")
            for category in categories:
                category_mapped = MAPPING.get(category, Category.Inconclusive)
                if category_mapped != Category.Inconclusive:
                    data[category_mapped].append(
                        {
                            "domain": md5(
                                row["origin"].encode(), usedforsecurity=False
                            ).hexdigest()
                        }
                    )
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
    "",
    "--csv-path",
    help="Path to CSV file containing the source data",
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
    delete_existing_records: bool = delete_existing_records_option,
    dry_run: bool = dry_run_option,
    server: str = server_option,
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
            delete_existing_records=delete_existing_records,
            dry_run=dry_run,
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
    server: str,
):
    csv_reader = csv.DictReader(file_object)

    # Generate the full list of domains before creating the chunked uploader
    # so we can validate the source data before deleting existing records and
    # starting the upload.
    data = RelevancyData.csv_to_relevancy_data(csv_reader)
    for category in data:
        with ChunkedRemoteSettingsRelevancyUploader(
            auth=auth,
            bucket=bucket,
            chunk_size=chunk_size,
            collection=collection,
            dry_run=dry_run,
            record_type=RELEVANCY_RECORD_TYPE,
            server=server,
            suggestion_score_fallback=0,
            total_data_count=len(data[category]),
            category_name=category.name,
            category_code=category.value,
        ) as uploader:
            if delete_existing_records:
                uploader.delete_records()

            domains = data[category]
            for domain in domains:
                uploader.add_relevancy_data(domain)
