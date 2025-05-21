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

# from merino.jobs.utils.rs_uploader import RemoteSettingsUploader

# from merino.jobs.geonames_uploader.downloader import Geoname, GeonamesDownloader

# from merino.jobs.geonames_uploader import geonames, alternates
from merino.jobs.geonames_uploader.geonames import geonames_cmd
from merino.jobs.geonames_uploader.alternates import alternates_cmd

logger = logging.getLogger(__name__)

rs_settings = config.remote_settings
job_settings = config.jobs.geonames_uploader

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










# Options
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

geonames_url_format_option = typer.Option(
    job_settings.geonames_url_format,
    "--geonames-url-format",
    help="URL format of per-country geonames zip files on the GeoNames server",
)

country_option = typer.Option(
    job_settings.country,
    "--country",
    help="Country code of geonames to select",
)

geonames_record_type_option = typer.Option(
    job_settings.geonames_record_type,
    "--geonames-record-type",
    help="The `type` of each geonames remote settings record",
)

filter_expr_countries_by_population_threshold_option = typer.Option(
    job_settings.filter_expr_countries_by_population_threshold,
    "--filter-expr-country-by-population-threshold",
    help="xxxadw",
)

# population_thresholds_option = typer.Option(
#     job_settings.population_thresholds,
#     "--population-threshold",
#     help="xxxadw",
# )
# filter_expr_countries_option = typer.Option(
#     job_settings.filter_expr_countries,
#     "--filter-expr-country",
#     help="xxxadw",
# )

# population_thresholds_and_filter_expr_countries_option = typer.Option(
#     job_settings.population_thresholds_and_filter_expr_countries,
#     "--filter-expr-country",
#     help="xxxadw",
# )



alternates_record_type_option = typer.Option(
    job_settings.alternates_record_type,
    "--alternates-record-type",
    help="The `type` of each alternates remote settings record",
)

alternates_url_format_option = typer.Option(
    job_settings.alternates_url_format,
    "--alternates-url-format",
    help="URL format of per-country alternates zip files on the GeoNames server",
)

alternates_languages_option = typer.Option(
    job_settings.alternates_languages,
    "--alternates-language",
    help="Languages of alternates to include",
)



geonames_uploader_cmd = typer.Typer(
    name="geonames-uploader",
    help="Command for uploading GeoNames data from geonames.org to remote settings",
#     default="geonames"
)










@geonames_uploader_cmd.command()
def geonames(
    country: str = country_option,
#     filter_expr_countries_by_population_threshold: dict[int, list[str]] = filter_expr_countries_by_population_threshold_option,


#     population_thresholds: list[int] = population_thresholds_option,
#     filter_expr_countries: list[list[str]] = filter_expr_countries_option,

#     population_thresholds_and_filter_expr_countries: list[int | str] = population_thresholds_and_filter_expr_countries_option,
#     population_thresholds_and_filter_expr_countries: list[Any] = population_thresholds_and_filter_expr_countries_option,

    filter_expr_countries_by_population_threshold: str = filter_expr_countries_by_population_threshold_option,

    #XXXadw should never keep existing records
#     keep_existing_records: bool = keep_existing_records_option,
    geonames_record_type: str = geonames_record_type_option,
    geonames_url_format: str = geonames_url_format_option,
    rs_auth: str = rs_auth_option,
    rs_bucket: str = rs_bucket_option,
    rs_collection: str = rs_collection_option,
    rs_dry_run: bool = rs_dry_run_option,
    rs_server: str = rs_server_option,
):
    filter_expr_countries_by_population_threshold = {
        int(t): cs for t, cs in json.loads(filter_expr_countries_by_population_threshold).items()
    }
    print(str(filter_expr_countries_by_population_threshold))

    geonames_cmd(
        country=country,
        filter_expr_countries_by_population_threshold=filter_expr_countries_by_population_threshold,
        geonames_record_type=geonames_record_type,
        geonames_url_format=geonames_url_format,
        rs_auth=rs_auth,
        rs_bucket=rs_bucket,
        rs_collection=rs_collection,
        rs_dry_run=rs_dry_run,
        rs_server=rs_server,
    )

# @geonames_uploader_cmd.command()
# def alternates():
# #     alternates_cmd()
#     pass

@geonames_uploader_cmd.command()
def alternates(
    alternates_languages: list[str] = alternates_languages_option,
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
    alternates_cmd(
        alternates_languages=alternates_languages,
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




# @geonames_uploader_cmd.command()
# def upload(

#     alternates_path: str = alternates_path_option,
#     base_url: str = base_url_option,


#     keep_existing_records: bool = keep_existing_records_option,

#     geonames_record_type: str = geonames_record_type_option,
#     alternates_record_type: str = alternates_record_type_option,
#     geonames_path: str = geonames_path_option,
#     filter_expression_countries: list[str] = filter_expression_countries_option,
#     filter_expression_locales: list[str] = filter_expression_locales_option,
#     geonames_countries: list[str] = geonames_countries_option,
#     alternates_iso_languages: list[str] = alternates_iso_languages_option,
#     population_thresholds: list[int] = population_thresholds_option,

#     filter_expression_countries_per_population_threshold: list[list[str]] =filter_expression_countries_per_population_threshold_option,

#     filter_expression_countries_per_population_threshold2: dict[int, list[str]] = filter_expression_countries_per_population_threshold2_option,

#     rs_auth: str = rs_auth_option,
#     rs_bucket: str = rs_bucket_option,
#     rs_collection: str = rs_collection_option,
#     rs_dry_run: bool = rs_dry_run_option,
#     rs_server: str = rs_server_option,

# ):
#     """Download GeoNames data from the GeoNames server, apply some processing
#     and selection, and upload it to remote settings.

#     """

#     thresholds_descending = sorted(population_thresholds, reverse=True)
#     min_threshold = thresholds_descending[-1]
#     geonames_by_threshold_by_country: dict[str, dict[int, [Geoname]]] = {}

#     for country in geonames_countries:
#         downloader = GeonamesDownloader(
#             alternates_path=alternates_path,
#             base_url=base_url,
#             city_alternates_iso_languages=alternates_iso_languages,
#             country_code=country,
#             geonames_path=geonames_path,
#             population_threshold=min_threshold,
#             admin_alternates_iso_languages=alternates_iso_languages,
#         )

#         state = downloader.download()

#         for geoname_id, geoname in state.geonames_by_id.items():
#             threshold = next(t for t in thresholds_descending if t <= geoname.population)
#             geonames_by_threshold = geonames_by_threshold_by_country.setdefault(country, {})
#             geonames = geonames_by_threshold.setdefault(threshold, [])
#             geonames.append(geoname)

#     rs_uploader = RemoteSettingsUploader(
#         auth=rs_auth,
#         bucket=rs_bucket,
#         collection=rs_collection,
#         server=rs_server,
#         dry_run=rs_dry_run,
#     )

#     #XXXadw
#     if not keep_existing_records:
# #         uploader.delete_records()
#         pass

#     # Build the filter expression.
#     filter_list = []
#     if filter_expression_countries:
#         countries = ", ".join([f"'{c}'" for c in filter_expression_countries])
#         filter_list.append(f"env.country in [{countries}]")
#     if filter_expression_locales:
#         locales = ", ".join([f"'{l}'" for l in filter_expression_locales])
#         filter_list.append(f"env.locale in [{locales}]")
#     filter_expression = " && ".join(filter_list)
#     filter_expression_dict = { "filter_expression": filter_expression } if filter_expression else {}

#     for country, geonames_by_threshold in geonames_by_threshold_by_country.items():
#         all_record_ids: list[str] = []
#         base_record_id = f"geonames-{country}"
#         threshold_geonames_max_to_min = sorted(
#             geonames_by_threshold.items(),
#             key=lambda tg: tg[0],
#             reverse=True
#         )

#         upper_threshold: int | None = None
#         for lower_threshold, geonames in threshold_geonames_max_to_min:
#             record_id = "-".join(
#                 [s for s in [
#                     "geonames",
#                     country,
#                     _pretty_threshold(lower_threshold),
#                     _pretty_threshold(upper_threshold),
#                 ] if s is not None]
#             )
#             all_record_ids.append(record_id)

#             # Upload the core geonames record.
#             rs_uploader.upload(
#                 record={
#                     "id": record_id,
#                     "type": geonames_record_type,
#                     **filter_expression_dict,
#                 },
#                 attachment=[_jsonable_geoname(g) for g in geonames],
#             )

#             # Upload the alternates records, one per alternates language. Each
#             # will contain alternates in that language for all geonames for the
#             # current country and population segment.
#             alts_by_geoname_id_by_lang = {}
#             for geoname in geonames:
#                 for lang, alts in geoname.alternates_by_iso_language.items():
#                     alts_by_geoname_id = alts_by_geoname_id_by_lang.setdefault(lang, [])
#                     alts_by_geoname_id.append([geoname.id, alts])

#             print(f"****XXXadw alts_by_geoname_id_by_lang={alts_by_geoname_id_by_lang}")

#             for lang, alts_by_geoname_id in alts_by_geoname_id_by_lang.items():
#                 alts_record_id = f"{record_id}-{lang}"
#                 all_record_ids.append(alts_record_id)
#                 print(f"****XXXadw uploading alt")
#                 rs_uploader.upload(
#                     record={
#                         "id": alts_record_id,
#                         "type": alternates_record_type,
#                         **filter_expression_dict,
#                     },
#                     attachment={
#                         "language": lang,
#                         "names_by_geoname_id": alts_by_geoname_id,
#                     }
#                 )
#                 print(f"****XXXadw done uploading alt")

#             upper_threshold = lower_threshold


# #         rs_uploader.delete_records(lambda r: r["id"].startswith(base_record_id) and r["id"] not in all_record_ids)

# #         #XXXadw check keep_existing_records
# #         if not keep_existing_records:
# #             print(f"****XXXadw calling delete_if")
# #             rs_uploader.delete_if(
# #                 _delete_if_predicate,
# #                 geonames_record_type=geonames_record_type,
# #                 alternates_record_type=alternates_record_type,
# #                 country=country,
# #                 all_record_ids=all_record_ids,
# #             )
# #             print(f"****XXXadw done calling delete_if")

#         if not keep_existing_records:
#             print(f"****XXXadw calling delete_if")
#             rs_uploader.delete_if(
#                 lambda r: (
#                     r.get("type", None) in [geonames_record_type, alternates_record_type] and
#                     r.get("country", None) == country and
#                     r["id"] not in all_record_ids
#                 )
#             )
#             print(f"****XXXadw done calling delete_if")


# # def _record_id(base: str, lower_threshold: int, upper_threshold: int) -> str:
# #     "-".join([s if s is not None for s in [base, _pretty_threshold(lower_threshold), _pretty_threshold(upper_threshold)]])

# # def _record_id(base: str, country: str, lower_threshold: int, upper_threshold: int, *other) -> str:
# #     return "-".join([s for s in [base, country, _pretty_threshold(lower_threshold), _pretty_threshold(upper_threshold), *other] if s is not None])


# def _delete_if_predicate(
#     record: dict[str, Any],
#     *,
#     geonames_record_type: str,
#     alternates_record_type: str,
#     country: str,
#     all_record_ids: list[str],
# ) -> bool:
# #     print(f"*****XXXadw _delete_record_predicate, geonames_record_type={geonames_record_type} alternates_record_type={alternates_record_type} country={country} all_record_ids={all_record_ids} record={record}")
#     return (
#         record.get("type", None) in [geonames_record_type, alternates_record_type] and
#         record.get("country", None) == country and
#         record["id"] not in all_record_ids
#     )


# # lambda r: r["id"].startswith(base_record_id) and r["id"] not in all_record_ids)

# def _jsonable_geoname(geoname: Geoname) -> dict[str, Any]:
#     d = dict(vars(geoname))
#     del d["alternates_by_iso_language"]
#     for a in ["admin1_code", "admin2_code", "admin3_code", "admin4_code"]:
#         if a in d and d[a] is None:
#             del d[a]
#     return d

# def _pretty_threshold(value: int | None) -> str | None:
#     if value is None:
#         return None
#     if 1_000_000 <= value and value % 1_000_000 == 0:
#         return f"{int(value / 1_000_000)}m"
#     if 1_000 <= value and value % 1_000 == 0:
#         return f"{int(value / 1_000)}k"
#     return str(value)
