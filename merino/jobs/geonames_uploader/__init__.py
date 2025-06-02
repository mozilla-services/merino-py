"""CLI commands for the geonames-uploader job. See the `geonames-uploader.md`
doc for info on the job and `downloader.py` for documentation on GeoNames.

"""

import asyncio
import importlib
import io
import json
import logging
from zipfile import ZipFile
from typing import Any, Callable

import csv
import requests
import typer
from urllib.parse import urljoin
from tempfile import NamedTemporaryFile, TemporaryDirectory, TemporaryFile

from merino.configs import settings as config
from merino.jobs.geonames_uploader.geonames import geonames_cmd, Partition
from merino.jobs.geonames_uploader.alternates import alternates_cmd

logger = logging.getLogger(__name__)

rs_settings = config.remote_settings
job_settings = config.jobs.geonames_uploader

# Options
alternates_record_type_option = typer.Option(
    job_settings.alternates_record_type,
    "--alternates-record-type",
    help="The `type` field of geonames alternates records",
)

alternates_url_format_option = typer.Option(
    job_settings.alternates_url_format,
    "--alternates-url-format",
    help="URL of country-specific alternates zip files on the GeoNames server",
)

country_option = typer.Option(
    job_settings.country,
    "--country",
    help="The country whose geonames or alternates to upload",
)

geonames_record_type_option = typer.Option(
    job_settings.geonames_record_type,
    "--geonames-record-type",
    help="The `type` field of core geonames records",
)

geonames_url_format_option = typer.Option(
    job_settings.geonames_url_format,
    "--geonames-url-format",
    help="URL of country-specific geonames zip files on the GeoNames server",
)

languages_option = typer.Option(
    job_settings.languages,
    "--language",
    help="List of language codes of alternates to upload",
)

partitions_option = typer.Option(
    job_settings.partitions,
    "--partitions",
    help="JSON string of population thresholds and filter-expression countries",
)

rs_auth_option = typer.Option(
    rs_settings.auth,
    "--rs-auth",
    help="Remote settings authorization token",
)

rs_bucket_option = typer.Option(
    rs_settings.bucket,
    "--rs-bucket",
    help="Remote settings bucket",
)

rs_collection_option = typer.Option(
    rs_settings.collection,
    "--rs-collection",
    help="Remote settings collection ID",
)

rs_dry_run_option = typer.Option(
    rs_settings.dry_run,
    "--rs-dry-run",
    help="Log the records that would be uploaded but don't upload them",
)

rs_server_option = typer.Option(
    rs_settings.server,
    "--rs-server",
    help="Remote settings server",
)

geonames_uploader_cmd = typer.Typer(
    name="geonames-uploader",
    help="Uploads GeoNames data to remote settings",
)


class PartitionsError(Exception):
    """An error encountered parsing the `partitions` option."""

    pass


def _parse_partitions(partitions_json: str) -> list[Partition]:
    value = None
    try:
        value = json.loads(partitions_json)
    except json.decoder.JSONDecodeError:
        raise PartitionsError("Partitions string is not valid JSON")

    if isinstance(value, list):
        return [_parse_partitions_item(i) for i in value]

    raise PartitionsError("Partitions must be a list")


def _parse_partitions_item(value: Any) -> Partition:
    if isinstance(value, int):
        return Partition(threshold_in_thousands=value)

    if isinstance(value, list):
        if len(value) != 2:
            raise PartitionsError("Partitions list item must be a 2-tuple when a list")

        threshold = 0
        countries = []
        threshold_value, countries_value = value

        if isinstance(threshold_value, int):
            threshold = threshold_value
        else:
            raise PartitionsError("Theshold value must be an int")

        if isinstance(countries_value, str):
            countries = [countries_value]
        elif isinstance(countries_value, list):
            for i in countries_value:
                if not isinstance(i, str):
                    raise PartitionsError("Country list item must be a string")
            countries = countries_value
        else:
            raise PartitionsError("Country value must be a string or list of strings")

        return Partition(threshold_in_thousands=threshold, countries=countries)

    raise PartitionsError("Partitions list item must be a threshold or threshold-countries tuple")


@geonames_uploader_cmd.command()
def geonames(
    country: str = country_option,
    partitions: str = partitions_option,
    geonames_record_type: str = geonames_record_type_option,
    geonames_url_format: str = geonames_url_format_option,
    rs_auth: str = rs_auth_option,
    rs_bucket: str = rs_bucket_option,
    rs_collection: str = rs_collection_option,
    rs_dry_run: bool = rs_dry_run_option,
    rs_server: str = rs_server_option,
):
    """Perform the `geonames` command."""
    if not country:
        raise ValueError("Country is required")
    if not partitions:
        raise ValueError("Partitions is required")

    # `partitions` is a JSON string since it can't easily be represented in the
    # config files otherwise.
    parsed_partitions = _parse_partitions(partitions)

    geonames_cmd(
        country=country,
        partitions=parsed_partitions,
        geonames_record_type=geonames_record_type,
        geonames_url_format=geonames_url_format,
        rs_auth=rs_auth,
        rs_bucket=rs_bucket,
        rs_collection=rs_collection,
        rs_dry_run=rs_dry_run,
        rs_server=rs_server,
    )


@geonames_uploader_cmd.command()
def alternates(
    languages: list[str] = languages_option,
    alternates_record_type: str = alternates_record_type_option,
    alternates_url_format: str = alternates_url_format_option,
    geonames_record_type: str = geonames_record_type_option,
    country: str = country_option,
    rs_auth: str = rs_auth_option,
    rs_bucket: str = rs_bucket_option,
    rs_collection: str = rs_collection_option,
    rs_dry_run: bool = rs_dry_run_option,
    rs_server: str = rs_server_option,
):
    """Perform the `upload alternates` command."""
    if not country:
        raise ValueError("Country is required")
    if not languages:
        raise ValueError("Languages is required")

    alternates_cmd(
        languages=set(languages),
        alternates_record_type=alternates_record_type,
        alternates_url_format=alternates_url_format,
        country=country,
        geonames_record_type=geonames_record_type,
        rs_auth=rs_auth,
        rs_bucket=rs_bucket,
        rs_collection=rs_collection,
        rs_dry_run=rs_dry_run,
        rs_server=rs_server,
    )
