"""Geonames helpers for the geonames-uploader command. See downloader.py for
documentation on geonames.

"""

import logging
import math
from typing import Any, Mapping
from dataclasses import asdict, dataclass, field

from merino.jobs.utils.rs_client import RecordData, RemoteSettingsClient, filter_expression_dict
from merino.jobs.geonames_uploader.downloader import Geoname, download_geonames

logger = logging.getLogger(__name__)


# A representation of a `Geoname` appropriate for including in a geonames
# attachment.
RsGeoname = dict[str, Any]


@dataclass
class Partition:
    """A chunk of geonames partitioned by population threshold."""

    threshold: int
    client_countries: list[str] = field(default_factory=list)
    geonames: list[Geoname] = field(default_factory=list)


@dataclass
class GeonamesRecord:
    """A geonames record with inline record data and a list of geonames as its
    attachment.

    """

    data: RecordData
    geonames: list[RsGeoname]


@dataclass
class GeonamesUpload:
    """The result of a successful geonames records upload."""

    final_records: list[GeonamesRecord] = field(default_factory=list)
    uploaded_count: int = 0
    not_uploaded_count: int = 0
    deleted_count: int = 0


def upload_geonames(
    country: str,
    existing_geonames_records_by_id: Mapping[str, RecordData],
    force_reupload: bool,
    geonames_record_type: str,
    geonames_url_format: str,
    partitions: list[Partition],
    rs_client: RemoteSettingsClient,
) -> GeonamesUpload:
    """Download geonames from the geonames server for a given country and upload
    geonames records to remote settings.

    """
    logger.info(f"Uploading geonames records for country '{country}'")

    partitions_descending = sorted(partitions, key=lambda p: p.threshold, reverse=True)
    min_threshold = partitions_descending[-1].threshold

    # Download geonames from the geonames server.
    download = download_geonames(
        country=country,
        population_threshold=min_threshold,
        url_format=geonames_url_format,
    )

    # Add the geonames to their appropriate partitions.
    for geoname in download.geonames:
        partition = next(
            p for p in partitions_descending if p.threshold <= (geoname.population or 0)
        )
        partition.geonames.append(geoname)

    # Create a record for each partition.
    upload = GeonamesUpload()
    final_record_ids = set()
    partitions_ascending = list(reversed(partitions_descending))
    for i, partition in enumerate(partitions_ascending):
        lower_threshold = partition.threshold
        upper_threshold = (
            partitions_ascending[i + 1].threshold if i + 1 < len(partitions_ascending) else None
        )

        if not partition.geonames:
            logger.info(
                f"No geonames for country '{country}' in partition [{lower_threshold}, {upper_threshold})"
            )
            continue

        # Build the record.
        record_id = _record_id(
            country=country,
            lower_threshold=lower_threshold,
            upper_threshold=upper_threshold,
        )

        filter_dict = {}
        client_countries_dict = {}
        if partition.client_countries:
            filter_dict = filter_expression_dict(countries=partition.client_countries)
            client_countries_dict = {
                "client_countries": sorted(partition.client_countries),
            }

        record = {
            "id": record_id,
            "type": geonames_record_type,
            "country": country,
            **client_countries_dict,
            **filter_dict,
        }

        # Force re-upload if requested or the existing record is different.
        existing_record = existing_geonames_records_by_id.get(record_id)
        force_record = force_reupload or bool(
            existing_record and record != {k: existing_record.get(k) for k, v in record.items()}
        )

        geonames = [_rs_geoname(g) for g in partition.geonames]

        uploaded = rs_client.upload(
            record=record,
            attachment=geonames,
            existing_record=existing_record,
            force_reupload=force_record,
        )

        final_record_ids.add(record_id)
        upload.final_records.append(GeonamesRecord(data=record, geonames=geonames))
        if uploaded:
            upload.uploaded_count += 1
        else:
            upload.not_uploaded_count += 1

    # Delete existing records for the country that weren't uploaded above.
    for record_id, record in existing_geonames_records_by_id.items():
        if record_id not in final_record_ids:
            rs_client.delete_record(record_id)
            upload.deleted_count += 1

    return upload


def _rs_geoname(geoname: Geoname) -> RsGeoname:
    """Convert a `Geoname` to a dict appropriate for including in a geonames
    attachment.

    """
    key_map = {
        "country_code": "country",
        "admin1_code": "admin1",
        "admin2_code": "admin2",
        "admin3_code": "admin3",
        "admin4_code": "admin4",
    }

    d = asdict(
        geoname, dict_factory=lambda obj: {key_map.get(k, k): v for (k, v) in obj if v is not None}
    )

    # The client is prepared to handle null `ascii_name`s, so to save space in
    # RS, discard it if it's the same as `name`.
    if d.get("ascii_name") == d["name"]:
        del d["ascii_name"]

    return d


def _record_id(
    country: str,
    lower_threshold: int,
    upper_threshold: int | None = None,
) -> str:
    """Return a geonames record ID."""
    return "-".join(
        [
            s
            for s in [
                "geonames",
                country,
                _pretty_threshold(lower_threshold),
                _pretty_threshold(upper_threshold),
            ]
            if s is not None
        ]
    )


def _pretty_threshold(value: int | None) -> str | None:
    """Convert a numeric threshold to a pretty string."""
    if value is None:
        return None

    # Pad the value with zeroes using a width of 4 since we're representing
    # population thresholds in thousands. No reasonable city population
    # threshold should be larger than 9 million = 4 places.
    in_thousands = math.floor(value / 1_000)
    return f"{in_thousands:04}"
