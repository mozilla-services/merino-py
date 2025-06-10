"""CLI commands for the geonames-uploader job. See the `geonames-uploader.md`
doc for info on the job and `downloader.py` for documentation on GeoNames.

"""

from dataclasses import dataclass
import logging
from typing import Any, Iterable, Mapping, Tuple

import typer

from merino.configs import settings as config
from merino.jobs.geonames_uploader.geonames import upload_geonames, Partition
from merino.jobs.geonames_uploader.alternates import (
    upload_alternates,
    ALTERNATES_LANGUAGES_BY_CLIENT_LOCALE,
)

from merino.jobs.utils.rs_client import RecordData, RemoteSettingsClient


EN_CLIENT_LOCALES = ["en-CA", "en-GB", "en-US", "en-ZA"]


@dataclass
class CountryConfig:
    """Job configuration for a particular country."""

    geonames_partitions: list[Partition]
    supported_client_locales: list[str]


# Maps from country codes to job config. See `geonames-uploader.md`.
CONFIGS_BY_COUNTRY = {
    "CA": CountryConfig(
        geonames_partitions=[
            Partition(threshold=50_000, client_countries=["CA"]),
            Partition(threshold=250_000, client_countries=["CA", "US"]),
            Partition(threshold=500_000),
        ],
        supported_client_locales=EN_CLIENT_LOCALES,
    ),
    "DE": CountryConfig(
        geonames_partitions=[
            Partition(threshold=50_000, client_countries=["DE"]),
            Partition(threshold=500_000),
        ],
        supported_client_locales=["de"],
    ),
    "FR": CountryConfig(
        geonames_partitions=[
            Partition(threshold=50_000, client_countries=["FR"]),
            Partition(threshold=500_000),
        ],
        supported_client_locales=["fr"],
    ),
    "GB": CountryConfig(
        geonames_partitions=[
            Partition(threshold=50_000, client_countries=["GB"]),
            Partition(threshold=500_000),
        ],
        supported_client_locales=EN_CLIENT_LOCALES,
    ),
    "IT": CountryConfig(
        geonames_partitions=[
            Partition(threshold=50_000, client_countries=["IT"]),
            Partition(threshold=500_000),
        ],
        supported_client_locales=["it"],
    ),
    "PL": CountryConfig(
        geonames_partitions=[
            Partition(threshold=50_000, client_countries=["PL"]),
            Partition(threshold=500_000),
        ],
        supported_client_locales=["pl"],
    ),
    "US": CountryConfig(
        geonames_partitions=[
            # There are a lot of US geonames in the range [50k, 250k), so break
            # it up into two smaller partitions to keep attachment sizes down.
            Partition(threshold=50_000, client_countries=["US"]),
            Partition(threshold=100_000, client_countries=["US"]),
            Partition(threshold=250_000, client_countries=["CA", "US"]),
            Partition(threshold=500_000),
        ],
        supported_client_locales=EN_CLIENT_LOCALES,
    ),
}

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

force_reupload_option = typer.Option(
    False,
    "--force-reupload",
    help="Recreate records and attachments even if they haven't changed",
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


@geonames_uploader_cmd.command()
def upload(
    alternates_record_type: str = alternates_record_type_option,
    alternates_url_format: str = alternates_url_format_option,
    force_reupload: bool = force_reupload_option,
    geonames_record_type: str = geonames_record_type_option,
    geonames_url_format: str = geonames_url_format_option,
    rs_auth: str = rs_auth_option,
    rs_bucket: str = rs_bucket_option,
    rs_collection: str = rs_collection_option,
    rs_dry_run: bool = rs_dry_run_option,
    rs_server: str = rs_server_option,
):
    """Perform the `upload` command."""
    _upload(
        alternates_record_type=alternates_record_type,
        alternates_url_format=alternates_url_format,
        force_reupload=force_reupload,
        geonames_record_type=geonames_record_type,
        geonames_url_format=geonames_url_format,
        rs_auth=rs_auth,
        rs_bucket=rs_bucket,
        rs_collection=rs_collection,
        rs_dry_run=rs_dry_run,
        rs_server=rs_server,
    )


def _upload(
    alternates_record_type: str,
    alternates_url_format: str,
    force_reupload: bool,
    geonames_record_type: str,
    geonames_url_format: str,
    rs_auth: str,
    rs_bucket: str,
    rs_collection: str,
    rs_dry_run: bool,
    rs_server: str,
    configs_by_country: Mapping[str, CountryConfig] = CONFIGS_BY_COUNTRY,
    alternates_languages_by_client_locale: Mapping[
        str, Iterable[str]
    ] = ALTERNATES_LANGUAGES_BY_CLIENT_LOCALE,
):
    locales_by_country = {
        country: data.supported_client_locales for country, data in configs_by_country.items()
    }

    rs_client = RemoteSettingsClient(
        auth=rs_auth,
        bucket=rs_bucket,
        collection=rs_collection,
        server=rs_server,
        dry_run=rs_dry_run,
    )

    # Get existing geonames and alternates records.
    existing_geonames_records_by_id_by_country, existing_alts_records_by_id_by_country = (
        _get_geonames_and_alternates_records(
            alternates_record_type=alternates_record_type,
            countries=set(configs_by_country.keys()),
            geonames_record_type=geonames_record_type,
            rs_client=rs_client,
        )
    )

    # Upload records for each country.
    for country, data in configs_by_country.items():
        # Upload geonames records.
        final_geonames_records = upload_geonames(
            country=country,
            existing_geonames_records_by_id=existing_geonames_records_by_id_by_country.get(
                country, {}
            ),
            force_reupload=force_reupload,
            geonames_record_type=geonames_record_type,
            geonames_url_format=geonames_url_format,
            partitions=data.geonames_partitions,
            rs_client=rs_client,
        )

        # Upload alternates records.
        upload_alternates(
            alternates_languages_by_client_locale=alternates_languages_by_client_locale,
            alternates_record_type=alternates_record_type,
            alternates_url_format=alternates_url_format,
            country=country,
            existing_alternates_records_by_id=existing_alts_records_by_id_by_country.get(
                country, {}
            ),
            force_reupload=force_reupload,
            geonames_record_type=geonames_record_type,
            geonames_records=final_geonames_records,
            locales_by_country=locales_by_country,
            rs_client=rs_client,
        )


def _get_geonames_and_alternates_records(
    alternates_record_type: str,
    countries: set[str],
    geonames_record_type: str,
    rs_client: RemoteSettingsClient,
) -> Tuple[Mapping[str, Mapping[str, RecordData]], Mapping[str, Mapping[str, RecordData]]]:
    geonames_records_by_id_by_country: dict[str, dict[str, dict[str, Any]]] = {}
    alts_records_by_id_by_country: dict[str, dict[str, dict[str, Any]]] = {}
    for record in rs_client.get_records():
        country = record.get("country")
        if country in countries and (record_id := record.get("id")):
            if record.get("type") == geonames_record_type:
                geonames_records_by_id_by_country.setdefault(country, {})[record_id] = record
            elif record.get("type") == alternates_record_type:
                alts_records_by_id_by_country.setdefault(country, {})[record_id] = record
    return (geonames_records_by_id_by_country, alts_records_by_id_by_country)
