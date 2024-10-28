"""CLI commands for the geonames_uploader module. See downloader.py for
documentation on GeoNames.

"""

import asyncio
import importlib
import io
import logging
from zipfile import ZipFile
from typing import Any, Callable

import csv
import requests
import typer
from urllib.parse import urljoin
from tempfile import NamedTemporaryFile, TemporaryDirectory, TemporaryFile

from merino.config import settings as config
from merino.jobs.csv_rs_uploader.chunked_rs_uploader import (
    ChunkedRemoteSettingsSuggestionUploader,
)
from merino.jobs.utils.chunked_rs_uploader import Chunk, ChunkedRemoteSettingsUploader
from merino.jobs.geonames_uploader.downloader import Geoname, GeonamesDownloader

logger = logging.getLogger(__name__)

rs_settings = config.remote_settings
job_settings = config.jobs.geonames_uploader

# Options
alternates_path_option = typer.Option(
    job_settings.alternates_path,
    "--alternates-path",
    help="Path of alternate names on the GeoNames server",
)

auth_option = typer.Option(
    rs_settings.auth,
    "--auth",
    help="Remote settings authorization token",
)

base_url_option = typer.Option(
    job_settings.base_url,
    "--base-url",
    help="Base URL of the GeoNames server",
)

bucket_option = typer.Option(
    rs_settings.bucket,
    "--bucket",
    help="Remote settings bucket",
)

chunk_size_option = typer.Option(
    rs_settings.chunk_size,
    "--chunk-size",
    help="The number of geonames to store in each attachment",
)

city_alternates_iso_languages_option = typer.Option(
    job_settings.city_alternates_iso_languages,
    "--city-alternates-iso-languages",
    help="Alternate city name languages and types to select",
)

collection_option = typer.Option(
    rs_settings.collection,
    "--collection",
    help="Remote settings collection ID",
)

country_code_option = typer.Option(
    job_settings.country_code,
    "--country-code",
    help="Country code of geonames to select",
)

dry_run_option = typer.Option(
    rs_settings.dry_run,
    "--dry-run",
    help="Log the records that would be uploaded but don't upload them",
)

geonames_path_option = typer.Option(
    job_settings.geonames_path,
    "--geonames-path",
    help="Path of geonames on the GeoNames server",
)

keep_existing_records_option = typer.Option(
    False,
    "--keep-existing-records",
    help="Keep existing records not present in the new data",
)

population_threshold_option = typer.Option(
    job_settings.population_threshold,
    "--population-threshold",
    help="Population threshold of geonames to select",
)

record_type_option = typer.Option(
    job_settings.record_type,
    "--record-type",
    help="The `type` of each remote settings record",
)

region_alternates_iso_languages_option = typer.Option(
    job_settings.region_alternates_iso_languages,
    "--region-alternates-iso-languages",
    help="Alternate region name languages and types to select",
)

server_option = typer.Option(
    rs_settings.server,
    "--server",
    help="Remote settings server",
)

geonames_uploader_cmd = typer.Typer(
    name="geonames-uploader",
    help="Command for uploading GeoNames data from geonames.org to remote settings",
)


class GeonamesChunk(Chunk):
    """A chunk of geonames to be uploaded in a single attachment."""

    max_alternate_name_length: int
    max_alternate_name_word_count: int

    @staticmethod
    def item_to_json_serializable(geoname: Geoname) -> Any:
        """Convert the geoname to a JSON serializable object."""
        return geoname.to_json_serializable()

    def __init__(self, start_index: int):
        super().__init__(start_index)
        self.max_alternate_name_length = 0
        self.max_alternate_name_word_count = 0

    def add_item(self, geoname: Geoname) -> None:
        """Add a geoname to the chunk."""
        super().add_item(geoname)
        for name in geoname.alternate_names:
            if len(name) > self.max_alternate_name_length:
                self.max_alternate_name_length = len(name)
            word_count = len(name.split())
            if word_count > self.max_alternate_name_word_count:
                self.max_alternate_name_word_count = word_count

    def to_json_serializable(self) -> Any:
        """Convert the chunk to a JSON serializable object that will be stored
        in the chunk's attachment.

        """
        return {
            "max_alternate_name_length": self.max_alternate_name_length,
            "max_alternate_name_word_count": self.max_alternate_name_word_count,
            "geonames": self.items,
        }


@geonames_uploader_cmd.command()
def upload(
    alternates_path: str = alternates_path_option,
    auth: str = auth_option,
    base_url: str = base_url_option,
    bucket: str = bucket_option,
    chunk_size: int = chunk_size_option,
    collection: str = collection_option,
    country_code: str = country_code_option,
    dry_run: bool = dry_run_option,
    geonames_path: str = geonames_path_option,
    city_alternates_iso_languages: list[str] = city_alternates_iso_languages_option,
    keep_existing_records: bool = keep_existing_records_option,
    population_threshold: int = population_threshold_option,
    record_type: str = record_type_option,
    region_alternates_iso_languages: list[str] = region_alternates_iso_languages_option,
    server: str = server_option,
):
    """Download GeoNames data from the GeoNames server, apply some processing
    and selection, and upload it to remote settings.

    """
    downloader = GeonamesDownloader(
        alternates_path=alternates_path,
        base_url=base_url,
        city_alternates_iso_languages=city_alternates_iso_languages,
        country_code=country_code,
        geonames_path=geonames_path,
        population_threshold=population_threshold,
        region_alternates_iso_languages=region_alternates_iso_languages,
    )
    state = downloader.download()

    with ChunkedRemoteSettingsUploader(
        allow_delete=True,
        auth=auth,
        bucket=bucket,
        chunk_cls=GeonamesChunk,
        chunk_size=chunk_size,
        collection=collection,
        dry_run=dry_run,
        record_type=record_type,
        server=server,
        total_item_count=len(state.geonames),
    ) as uploader:
        if not keep_existing_records:
            uploader.delete_records()

        for g in state.geonames:
            uploader.add_item(g)
