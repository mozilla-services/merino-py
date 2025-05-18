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

from merino.jobs.utils.rs_client import RemoteSettingsClient

# from merino.jobs.geonames_uploader.downloader import Geoname, GeonamesDownloader
from merino.jobs.geonames_uploader.downloader import download_alternates

logger = logging.getLogger(__name__)

# rs_settings = config.remote_settings
# job_settings = config.jobs.geonames_uploader

# # Options
# alternates_path_option = typer.Option(
#     job_settings.alternates_path,
#     "--alternates-path",
#     help="Path of alternate names on the GeoNames server",
# )

# rs_auth_option = typer.Option(
#     rs_settings.auth,
#     "--auth",
#     help="Remote settings authorization token",
# )

# base_url_option = typer.Option(
#     job_settings.base_url,
#     "--base-url",
#     help="Base URL of the GeoNames server",
# )

# rs_bucket_option = typer.Option(
#     rs_settings.bucket,
#     "--bucket",
#     help="Remote settings bucket",
# )

# alternates_iso_languages_option = typer.Option(
#     job_settings.alternates_iso_languages,
#     "--alternates-iso-language",
#     help="Languages and types to select for alternates",
# )

# rs_collection_option = typer.Option(
#     rs_settings.collection,
#     "--collection",
#     help="Remote settings collection ID",
# )

# geonames_countries_option = typer.Option(
#     job_settings.geonames_countries,
#     "--geonames-country",
#     help="Country codes of geonames to select",
# )

# rs_dry_run_option = typer.Option(
#     rs_settings.dry_run,
#     "--dry-run",
#     help="Log the records that would be uploaded but don't upload them",
# )

# geonames_path_option = typer.Option(
#     job_settings.geonames_path,
#     "--geonames-path",
#     help="Path of geonames on the GeoNames server",
# )

# keep_existing_records_option = typer.Option(
#     False,
#     "--keep-existing-records",
#     help="Keep existing records not present in the new data",
# )

# population_thresholds_option = typer.Option(
#     job_settings.population_thresholds,
#     "--population-threshold",
#     help="Population thresholds of geonames to select",
# )

# geonames_record_type_option = typer.Option(
#     job_settings.geonames_record_type,
#     "--geonames-record-type",
#     help="The `type` of each geonames remote settings record",
# )

# rs_server_option = typer.Option(
#     rs_settings.server,
#     "--server",
#     help="Remote settings server",
# )


# filter_expression_countries_option = typer.Option(
#     job_settings.filter_expression_countries,
#     "--filter-expression-country",
#     help="XXXadw",
# )

# filter_expression_locales_option = typer.Option(
#     job_settings.filter_expression_locales,
#     "--filter-expression-locale",
#     help="XXXadw",
# )

# alternates_record_type_option = typer.Option(
#     job_settings.alternates_record_type,
#     "--alternates-record-type",
#     help="The `type` of each alternates remote settings record",
# )



# filter_expression_countries_per_population_threshold_option = typer.Option(
#     job_settings.filter_expression_countries_per_population_threshold,
#     "--xxxadw",
#     help="xxxadw",
# )

# filter_expression_countries_per_population_threshold2_option = typer.Option(
#     job_settings.filter_expression_countries_per_population_threshold2,
#     "--xxxadw",
#     help="xxxadw",
# )



# geonames_uploader_cmd = typer.Typer(
#     name="geonames-uploader",
#     help="Command for uploading GeoNames data from geonames.org to remote settings",
# )




# geonames_uploader_cmd = typer.Typer(
#     name="geonames-uploader",
#     help="Command for uploading GeoNames data from geonames.org to remote settings",
# )

# @geonames_uploader_cmd.command()
# def alternates():
#     print("alternates cmd")



# def alternates_cmd():
#     print("alternates cmd")

# @geonames_uploader_cmd.command()
# def alternates(
#     alternates_record_type: str = alternates_record_type_option,
#     country: list[str] = country_option,
#     languages: list[str] = languages_option,
#     geonames_record_type: str = geonames_record_type_option,
#     url: str = url_option,
#     rs_bucket: str = rs_bucket_option,
#     rs_collection: str = rs_collection_option,
#     rs_dry_run: bool = rs_dry_run_option,
#     rs_server: str = rs_server_option,
# ):
#     rs_client = RemoteSettingsClient(
#         auth=rs_auth,
#         bucket=rs_bucket,
#         collection=rs_collection,
#         server=rs_server,
#         dry_run=rs_dry_run,
#     )

# #     geonames_records = rs_client.filter_records(lambda r: (
# #         r.get("type") == geonames_record_type and
# #         r.get("country") == country
# #     ))
# #     if not geonames_records:
# #         logger.info(f"No records for country '{country}' in remote settings")
# #         return

# #     geonames_records = []
# #     existing_alternates_records = []
# #     for record in rs_client.get_records():
# #         match record.get("type"):
# #             case geonames_record_type:
# #                 if record.get("country") == country:
# #                     geonames_records.append(record)
# #             case alternates_record_type:
# #                 if record.get("country") == country and record.get("language") in languages:
# #                     existing_alternates_records.append(record)

#     geonames_records = []
#     existing_alternates_records = []
#     for record in rs_client.get_records():
#         if record.get("type") == geonames_record_type and record.get("country") == country:
#             geonames_records.append(record)
#         elif record.get("type") == alternates_record_type and record.get("country") == country and record.get("language") in languages:
#             existing_alternates_records.append(record)

#     if not geonames_records:
#         logger.info(f"No records for country '{country}' in remote settings")
#         return

# #     geoname_ids_by_threshold: dict[int, list[int]] = {}
# #     for record in geonames_records:
# # #         lower_threshold = record["lower_population_threshold"]
# # #         upper_threshold = record["upper_population_threshold"]
# #         threshold = record["lower_population_threshold"]
# #         geoname_ids = geoname_ids_by_threshold.setdefault(threshold, [])
# #         geonames = rs.client.download_attachment(record)
# #         if geonames:
# #             for geoname in geonames:
# #                 geoname_ids.append(geoname.id)

#     geoname_ids_by_record_id: dict[str, list[int]] = {}
#     for record in geonames_records:
#         geonames = rs.client.download_attachment(record)
#         if geonames:
#             geoname_ids = []
#             geoname_ids_by_record_id[record["id"]] = geonames_ids
#             for g in geonames:
#                 geoname_ids.append(g.id)

# #     downloader = GeonamesAlternatesDownloader(
# #         country=country,
# #         languages=languages,
# #         url=url,
# #     )
# #     state = downloader.download()

#     state = download_alternates(
#         country=country,
# #         geoname_ids
#         languages=languages,
#         url_format=url_format,
#     )
#     state = downloader.download()

#     #XXXadw warn if selected languages aren't available

#     uploaded_record_ids = set()
#     for lang in state.languages:
#         for record_id, geoname_ids in geoname_ids_by_record_id.items():
#             alternates_by_geoname_id: list[[int, list[str]]] = []
#             for geoname_id in geoname_ids:
#                 alts = state.get_alternates(geoname_id, lang)
#                 if alts:
#                     alternates_by_geoname_id.append([geoname_id, alts])
#             if alternates_by_geoname_id:
#                 alts_record_id = f"{record_id}-{lang}"
#                 uploaded_record_ids.add(alts_record_id)
#                 rs_client.upload(
#                     record={
#                         "id": alts_record_id,
#                         "type": alternates_record_type,
#                     },
#                     attachment=alternates_by_geoname_id,
#                 )

# #     rs_client.delete_if(lambda r: (
# #         r.get("type") == alternates_record_type and
# #         r.get("country") == country
# #     ))

#     for record in existing_alternates_records:
#         if record["id"] not in uploaded_record_ids:
#             rs_client.delete_record(record["id"])












def alternates_cmd(
    alternates_languages: list[str],
    alternates_record_type: str,
    alternates_url_format: str,
    country: list[str],
    geonames_record_type: str,
    rs_auth: str,
    rs_bucket: str,
    rs_collection: str,
    rs_dry_run: bool,
    rs_server: str,
):
    rs_client = RemoteSettingsClient(
        auth=rs_auth,
        bucket=rs_bucket,
        collection=rs_collection,
        server=rs_server,
        dry_run=rs_dry_run,
    )

#     geonames_records = rs_client.filter_records(lambda r: (
#         r.get("type") == geonames_record_type and
#         r.get("country") == country
#     ))
#     if not geonames_records:
#         logger.info(f"No records for country '{country}' in remote settings")
#         return

#     geonames_records = []
#     existing_alternates_records = []
#     for record in rs_client.get_records():
#         match record.get("type"):
#             case geonames_record_type:
#                 if record.get("country") == country:
#                     geonames_records.append(record)
#             case alternates_record_type:
#                 if record.get("country") == country and record.get("language") in languages:
#                     existing_alternates_records.append(record)

    geonames_records = []
    existing_alternates_records = []
    for record in rs_client.get_records():
        if record.get("type") == geonames_record_type and record.get("country") == country:
            geonames_records.append(record)
        elif record.get("type") == alternates_record_type and record.get("country") == country and record.get("language") in alternates_languages:
            existing_alternates_records.append(record)

    if not geonames_records:
        logger.info(f"No records for country '{country}' in remote settings")
        return

#     geoname_ids_by_threshold: dict[int, list[int]] = {}
#     for record in geonames_records:
# #         lower_threshold = record["lower_population_threshold"]
# #         upper_threshold = record["upper_population_threshold"]
#         threshold = record["lower_population_threshold"]
#         geoname_ids = geoname_ids_by_threshold.setdefault(threshold, [])
#         geonames = rs_client.download_attachment(record)
#         if geonames:
#             for geoname in geonames:
#                 geoname_ids.append(geoname.id)

#     geoname_ids_by_record_id: dict[str, list[int]] = {}
#     for record in geonames_records:
#         geonames = rs_client.download_attachment(record)
#         if geonames:
#             geoname_ids = []
#             geoname_ids_by_record_id[record["id"]] = geoname_ids
#             for g in geonames:
#                 geoname_ids.append(g["id"])

#     uploaded_record_ids = set()
#     for record_id, geoname_ids in geoname_ids_by_record_id.items():
#         state = download_alternates(
#             country=country,
#             geoname_ids=geoname_ids,
#             languages=alternates_languages,
#             url_format=alternates_url_format,
#         )
#         for lang in alternates_languages:
#             names_by_geoname_id = state.names_by_geoname_id_by_language.get(lang)
#             if not names_by_geoname_id:
#                 logger.warn(f"No alternates for record '{record_id}' with language '{lang}'")
#                 continue
#             alts_record_id = f"{record_id}-{lang}"
#             uploaded_record_ids.add(alts_record_id)
#             rs_client.upload(
#                 record={
#                     "id": alts_record_id,
#                     "type": alternates_record_type,
#                     "country": country,
#                     "language": lang,
#                 },
#                 attachment={
#                     "language": lang,
#                     "names_by_geoname_id": list(names_by_geoname_id.items()),
#                 }
#             )


#     geonames_by_record_id: dict[str, list[dict[str, Any]]] = {}
#     for record in geonames_records:
#         geonames_by_record_id[record["id"]] = rs_client.download_attachment(record)

#     geonames_by_record_id = {record["id"]: rs_client.download_attachment(record)}

#     uploaded_record_ids = set()
#     for record_id, geonames in geonames_by_record_id.items():
#         state = download_alternates(
#             country=country,
# #             geoname_ids=set(g["id"] for g in geoname_ids),
#             geonames_by_id=geonames_by_id,
#             languages=alternates_languages,
#             url_format=alternates_url_format,
#         )
#         for lang in alternates_languages:
#             names_by_geoname_id = state.names_by_geoname_id_by_language.get(lang)
#             if not names_by_geoname_id:
#                 logger.warn(f"No alternates for record '{record_id}' with language '{lang}'")
#                 continue
#             alts_record_id = f"{record_id}-{lang}"
#             uploaded_record_ids.add(alts_record_id)
#             rs_client.upload(
#                 record={
#                     "id": alts_record_id,
#                     "type": alternates_record_type,
#                     "country": country,
#                     "language": lang,
#                 },
#                 attachment={
#                     "language": lang,
#                     "names_by_geoname_id": list(names_by_geoname_id.items()),
#                 }
#             )



#     geonames = rs_client.download_attachment(record)
#     geonames_by_id_by_record_id = {
#         record["id"]: {g["id"] for g in rs_client.download_attachment(record)}


#     geonames_by_id_by_record_id: dict[str, dict[int, dict[str, Any]]] = {}
#     for record in geonames_records:
#         geonames = rs_client.download_attachment(record)
#         geonames_by_id_by_record_id[record["id"]] = {g["id"]: g for g in geonames}

#     uploaded_record_ids = set()
#     for record_id, geonames_by_id in geonames_by_id_by_record_id.items():
#         state = download_alternates(
#             country=country,
# #             geoname_ids=set(g["id"] for g in geoname_ids),
#             geonames_by_id=geonames_by_id,
#             languages=alternates_languages,
#             url_format=alternates_url_format,
#         )
#         for lang in alternates_languages:
#             names_by_geoname_id = state.names_by_geoname_id_by_language.get(lang)
#             if not names_by_geoname_id:
#                 logger.warn(f"No alternates for record '{record_id}' with language '{lang}'")
#                 continue
#             alts_record_id = f"{record_id}-{lang}"
#             uploaded_record_ids.add(alts_record_id)
#             rs_client.upload(
#                 record={
#                     "id": alts_record_id,
#                     "type": alternates_record_type,
#                     "country": country,
#                     "language": lang,
#                 },
#                 attachment={
#                     "language": lang,
#                     "names_by_geoname_id": list(names_by_geoname_id.items()),
#                 }
#             )


    geonames_by_id_by_record: list[dict[str, Any], dict[int, dict[str, Any]]] = []
    for record in geonames_records:
        geonames = rs_client.download_attachment(record)
        geonames_by_id_by_record.append([record, {g["id"]: g for g in geonames}])

    uploaded_record_ids = set()
    for record, geonames_by_id in geonames_by_id_by_record:
        record_id = record["id"]
        filter_expr = record.get("filter_expression")
        filter_expr_dict = {"filter_expression": filter_expr} if filter_expr else {}

        state = download_alternates(
            country=country,
#             geoname_ids=set(g["id"] for g in geoname_ids),
            geonames_by_id=geonames_by_id,
            languages=alternates_languages,
            url_format=alternates_url_format,
        )
        for lang in alternates_languages:
            names_by_geoname_id = state.names_by_geoname_id_by_language.get(lang)
            if not names_by_geoname_id:
                logger.warn(f"No alternates for record '{record_id}' with language '{lang}'")
                continue
            alts_record_id = f"{record_id}-{lang}"
            uploaded_record_ids.add(alts_record_id)
            rs_client.upload(
                record={
                    "id": alts_record_id,
                    "type": alternates_record_type,
                    "country": country,
                    "language": lang,
                    **filter_expr_dict,
                },
                attachment={
                    "language": lang,
                    "names_by_geoname_id": list(names_by_geoname_id.items()),
                }
            )



#     rs_client.delete_if(lambda r: (
#         r.get("type") == alternates_record_type and
#         r.get("country") == country
#     ))

    for record in existing_alternates_records:
        if record["id"] not in uploaded_record_ids:
            rs_client.delete_record(record["id"])
