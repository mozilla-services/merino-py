"""CLI commands for the geonames_uploader module. See downloader.py for
documentation on GeoNames.

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

from merino.jobs.utils.rs_uploader import RemoteSettingsUploader

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

client_countries_option = typer.Option(
    job_settings.client_countries,
    "--client-country",
    help="XXXadw",
)

client_locales_option = typer.Option(
    job_settings.client_locales,
    "--client-locale",
    help="XXXadw",
)

geoname_countries_option = typer.Option(
    job_settings.geoname_countries,
    "--geoname-country",
    help="XXXadw",
)

dry_run_option = typer.Option(
    rs_settings.dry_run,
    "--dry-run",
    help="Log the records that would be uploaded but don't upload them",
)

filter_expression = typer.Option(
    rs_settings.filter_expression,
    "--filter-expression",
    help="Filter expression to set on remote settings records",
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

population_thresholds_option = typer.Option(
    job_settings.population_thresholds,
    "--population-threshold",
    help="Population threshold of geonames to select",
)

geonames_record_type_option = typer.Option(
    job_settings.geonames_record_type,
    "--geonames-record-type",
    help="The `type` of each core geonames remote settings record",
)

alternates_record_type_option = typer.Option(
    job_settings.alternates_record_type,
    "--alternates-record-type",
    help="The `type` of each alternates remote settings record",
)

admin_alternates_iso_languages_option = typer.Option(
    job_settings.admin_alternates_iso_languages,
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

@geonames_uploader_cmd.command()
def upload(
    alternates_path: str = alternates_path_option,
    auth: str = auth_option,
    base_url: str = base_url_option,
    bucket: str = bucket_option,
    collection: str = collection_option,
    dry_run: bool = dry_run_option,
    server: str = server_option,
    keep_existing_records: bool = keep_existing_records_option,
    geonames_record_type: str = geonames_record_type_option,
    alternates_record_type: str = alternates_record_type_option,
    geonames_path: str = geonames_path_option,
    client_countries: list[str] = client_countries_option,
    client_locales: list[str] = client_locales_option,
    geoname_countries: list[str] = geoname_countries_option,
    city_alternates_iso_languages: list[str] = city_alternates_iso_languages_option,
    admin_alternates_iso_languages: list[str] = admin_alternates_iso_languages_option,
    population_thresholds: list[int] = population_thresholds_option,
):
    """Download GeoNames data from the GeoNames server, apply some processing
    and selection, and upload it to remote settings.

    """

    min_threshold = min(population_thresholds)
    thresholds_max_to_min = sorted(population_thresholds, reverse=True)
    geonames_by_threshold_by_country: dict[str, dict[int, [Geoname]]] = {}

    for country in geoname_countries:
        downloader = GeonamesDownloader(
            alternates_path=alternates_path,
            base_url=base_url,
            city_alternates_iso_languages=city_alternates_iso_languages,
            country_code=country,
            geonames_path=geonames_path,
            population_threshold=min_threshold,
            admin_alternates_iso_languages=admin_alternates_iso_languages,
        )

        state = downloader.download()

        for geoname_id, geoname in state.geonames_by_id.items():
            threshold = next(t for t in thresholds_max_to_min if t <= geoname.population)
            geonames_by_threshold = geonames_by_threshold_by_country.setdefault(country, {})
            geonames = geonames_by_threshold.setdefault(threshold, [])
            geonames.append(geoname)

    rs_uploader = RemoteSettingsUploader(
        auth=auth,
        bucket=bucket,
        collection=collection,
        server=server,
        dry_run=dry_run,
    )

    #XXXadw
    if not keep_existing_records:
#         uploader.delete_records()
        pass

    for country, geonames_by_threshold in geonames_by_threshold_by_country.items():
        previous_threshold: int | None = None
        for threshold, geonames in geonames_by_threshold.items():
            lower = _pretty_threshold(threshold)
            record_id = f"geonames-{country}-{lower}"
            if previous_threshold is not None:
                upper = _pretty_threshold(previous_threshold)
                record_id = f"{record_id}-{upper}"

            previous_threshold = threshold

            # core geonames record
            filter_countries = ", ".join([f"'{c}'" for c in client_countries])
            filter_locales = ", ".join([f"'{l}'" for l in client_locales])
            filter_expression_list = []
            if filter_countries:
                filter_expression_list.append(f"env.country in [{filter_countries}]")
            if filter_locales:
                filter_expression_list.append(f"env.locale in [{filter_locales}]")
            filter_expression = " && ".join(filter_expression_list)

            geonames_record = {
                "id": record_id,
                "type": geonames_record_type,
                "filter_expression": filter_expression,
            }
            geonames = [_jsonable_geoname(g) for g in geonames]
            rs_uploader.upload(record=geonames_record, attachment_json=json.dumps(geonames))

            #XXXadw alternates record


def _jsonable_geoname(geoname: Geoname) -> dict[str, Any]:
    d = dict(vars(geoname))
    del d["alternates_by_iso_language"]
    for a in ["admin1_code", "admin2_code", "admin3_code", "admin4_code"]:
        if a in d and d[a] is None:
            del d[a]
    return d

def _pretty_threshold(value: int) -> str:
    if 1_000_000 <= value and value % 1_000_000 == 0:
        return f"{int(value / 1_000_000)}m"
    if 1_000 <= value and value % 1_000 == 0:
        return f"{int(value / 1_000)}k"
    return str(value)
