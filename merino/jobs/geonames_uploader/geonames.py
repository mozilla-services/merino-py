"""CLI commands for the geonames_uploader module. See downloader.py for
documentation on GeoNames.

"""

import asyncio
import importlib
import io
# import json
import logging
from zipfile import ZipFile
from typing import Any, Callable

import csv
import requests
import typer
from urllib.parse import urljoin
from tempfile import NamedTemporaryFile, TemporaryDirectory, TemporaryFile

from merino.configs import settings as config

# from merino.jobs.utils.rs_uploader import RemoteSettingsUploader
from merino.jobs.utils.rs_client import RemoteSettingsClient

# from merino.jobs.geonames_uploader.downloader import Geoname, GeonamesDownloader
from merino.jobs.geonames_uploader.downloader import Geoname, download_geonames

# from merino.jobs.geonames_uploader import geonames_uploader_cmd


logger = logging.getLogger(__name__)

# rs_settings = config.remote_settings
# job_settings = config.jobs.geonames_uploader

# # Options
# rs_auth_option = typer.Option(
#     rs_settings.auth,
#     "--rs-auth",
#     help="Remote settings authorization token",
# )

# rs_bucket_option = typer.Option(
#     rs_settings.bucket,
#     "--rs-bucket",
#     help="Remote settings bucket",
# )

# rs_collection_option = typer.Option(
#     rs_settings.collection,
#     "--rs-collection",
#     help="Remote settings collection ID",
# )

# rs_dry_run_option = typer.Option(
#     rs_settings.dry_run,
#     "--rs-dry-run",
#     help="Log the records that would be uploaded but don't upload them",
# )

# rs_server_option = typer.Option(
#     rs_settings.server,
#     "--rs-server",
#     help="Remote settings server",
# )

# url_option = typer.Option(
#     job_settings.geonames_url,
#     "--url",
#     help="URL format of country zip files on the GeoNames server",
# )

# country_option = typer.Option(
#     job_settings.country,
#     "--country",
#     help="Country code of geonames to select",
# )

# record_type_option = typer.Option(
#     job_settings.geonames_record_type,
#     "--record-type",
#     help="The `type` of each geonames remote settings record",
# )

# filter_expr_countries_by_population_threshold_option = typer.Option(
#     job_settings.filter_expr_countries_by_population_threshold,
#     "--filter-expr-country-by-population-threshold",
#     help="xxxadw",
# )


# geonames_uploader_cmd = typer.Typer(
#     name="geonames-uploader",
#     help="Command for uploading GeoNames data from geonames.org to remote settings",
# )


# @geonames_uploader_cmd.command()
# def geonames(
#     country: list[str] = country_option,
#     filter_expr_countries_by_population_threshold: dict[int, list[str]] = filter_expr_countries_by_population_threshold_option,
#     #XXXadw should never keep existing records
# #     keep_existing_records: bool = keep_existing_records_option,
#     record_type: str = record_type_option,
#     url: str = url_option,
#     rs_auth: str = rs_auth_option,
#     rs_bucket: str = rs_bucket_option,
#     rs_collection: str = rs_collection_option,
#     rs_dry_run: bool = rs_dry_run_option,
#     rs_server: str = rs_server_option,
# ):

def geonames_cmd(
    country: str,
    filter_expr_countries_by_population_threshold: dict[int, list[str]],
    geonames_record_type: str,
    geonames_url_format: str,
    rs_auth: str,
    rs_bucket: str,
    rs_collection: str,
    rs_dry_run: bool,
    rs_server: str,
):

#     thresholds_and_filter_countries_descending = sorted(
#         filter_expr_countries_by_population_threshold.items(),
#         key=lambda t: t[0],
#         reverse=True
#     )
#     min_threshold = thresholds_and_filter_countries_descending[-1][0]

    thresholds_descending = sorted(
        filter_expr_countries_by_population_threshold.keys(),
        reverse=True
    )
    min_threshold = thresholds_descending[-1]

#     downloader = GeonamesDownloader(
#         country=country,
#         population_threshold=min_threshold,
#         url_format=geonames_url_format,
#     )
#     state = downloader.download()


    state = download_geonames(
        country=country,
        population_threshold=min_threshold,
        url_format=geonames_url_format,
    )

    geonames_by_threshold: dict[str, dict[int, [Geoname]]] = {}
    for geoname in state.geonames:
#         threshold_and_filter_countries = next(
#             t for t in thresholds_and_filter_countries_descending
#             if t[0] <= geoname.population
#         )
        threshold = next(t for t in thresholds_descending if t <= geoname.population)
        geonames = geonames_by_threshold.setdefault(threshold, [])
        geonames.append(geoname)

    rs_client = RemoteSettingsClient(
        auth=rs_auth,
        bucket=rs_bucket,
        collection=rs_collection,
        server=rs_server,
        dry_run=rs_dry_run,
    )

#     for threshold, filter_expr_countries in filter_expr_countries_by_population_threshold.items():

    uploaded_record_ids = set()
    previous_threshold = None
    for threshold in thresholds_descending:
        lower_threshold = threshold
        upper_threshold = previous_threshold
        previous_threshold = threshold

        # Build the filter expression.
        filter_expr_dict = {}
        filter_expr_countries = filter_expr_countries_by_population_threshold[threshold]
        if filter_expr_countries:
            countries_str = ", ".join([f"'{c}'" for c in filter_expr_countries])
            filter_expr_dict = { "filter_expression": f"env.country in [{countries_str}]"}

        record_id = "-".join(
            [s for s in [
                "geonames",
                country,
                _pretty_threshold(lower_threshold),
                _pretty_threshold(upper_threshold),
            ] if s is not None]
        )
        uploaded_record_ids.add(record_id)

        rs_client.upload(
            record={
                "id": record_id,
                "type": geonames_record_type,
                "country": country,
                **filter_expr_dict,
            },
            attachment=[_jsonable_geoname(g) for g in geonames_by_threshold[threshold]],
        )

    for record in rs_client.get_records():
        if record.get("type") == geonames_record_type and record["id"] not in uploaded_record_ids:
            rs_client.delete_record(record["id"])


# def _jsonable_geoname(geoname: Geoname) -> dict[str, Any]:
#     d = dict(vars(geoname))
# #     del d["alternates_by_iso_language"]
#     #XXXadw comment
#     if d.get("ascii_name") == d["name"]:
#         del d["ascii_name"]
#     for a in ["admin1_code", "admin2_code", "admin3_code", "admin4_code"]:
#         if a in d and d[a] is None:
#             del d[a]
#     return d

def _jsonable_geoname(geoname: Geoname) -> dict[str, Any]:
    key_map = {
        "id": "id",
        "name": "name",
        "feature_class": "feature_class",
        "feature_code": "feature_code",
        "country": "country_code",
        "admin1": "admin1_code",
        "admin2": "admin2_code",
        "admin3": "admin3_code",
        "admin4": "admin4_code",
        "population": "population",
        "ascii_name": "ascii_name",
        "latitude": "latitude",
        "longitude": "longitude",
    }
    s = dict(vars(geoname))
    d = {}
    for dk, sk in key_map.items():
        if s[sk] is not None:
            d[dk] = s[sk]

    if d.get("ascii_name") == d["name"]:
        del d["ascii_name"]

    return d

def _pretty_threshold(value: int | None) -> str | None:
    if value is None:
        return None
    if 1_000_000 <= value and value % 1_000_000 == 0:
        return f"{int(value / 1_000_000)}m"
    if 1_000 <= value and value % 1_000 == 0:
        return f"{int(value / 1_000)}k"
    return str(value)
