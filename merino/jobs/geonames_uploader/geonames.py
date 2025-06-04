"""CLI commands for the geonames_uploader module. See downloader.py for
documentation on GeoNames.

"""

import logging
from typing import Any
from dataclasses import asdict

from merino.jobs.utils.rs_client import RemoteSettingsClient, filter_expression_dict
from merino.jobs.geonames_uploader.downloader import Geoname, download_geonames

logger = logging.getLogger(__name__)


class Partition:
    """A chunk of geonames partitioned by population threshold."""

    threshold: int
    countries: list[str] | None
    geonames: list[Geoname]

    def __init__(self, threshold_in_thousands: int, countries: list[str] | None = None):
        """Create a new partition."""
        self.threshold = 1_000 * threshold_in_thousands
        self.countries = countries
        self.geonames = []

    def add_geoname(self, geoname: Geoname) -> None:
        """Add a geoname to the partition."""
        self.geonames.append(geoname)

    def __repr__(self) -> str:
        return str(vars(self))

    def __eq__(self, other) -> bool:
        return isinstance(other, Partition) and vars(self) == vars(other)


def geonames_cmd(
    country: str,
    partitions: list[Partition],
    geonames_record_type: str,
    geonames_url_format: str,
    rs_auth: str,
    rs_bucket: str,
    rs_collection: str,
    rs_dry_run: bool,
    rs_server: str,
):
    """Perform the `geonames` command, which uploads geonames to remote
    settings.

    """
    if not partitions:
        raise ValueError("At least one partition must be specified")

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
        partition.add_geoname(geoname)

    rs_client = RemoteSettingsClient(
        auth=rs_auth,
        bucket=rs_bucket,
        collection=rs_collection,
        server=rs_server,
        dry_run=rs_dry_run,
    )

    partitions_ascending = list(reversed(partitions_descending))

    # Create a record for each partition's geonames.
    uploaded_record_ids = set()
    for i, partition in enumerate(partitions_ascending):
        lower_threshold = partition.threshold
        upper_threshold = (
            partitions_ascending[i + 1].threshold if i + 1 < len(partitions_ascending) else None
        )

        if not partition.geonames:
            logger.warning(
                f"No geonames with populations in requested partition [{lower_threshold}, {upper_threshold})"
            )
            continue

        record_id = _record_id(
            country=country,
            lower_threshold=lower_threshold,
            upper_threshold=upper_threshold,
        )
        uploaded_record_ids.add(record_id)

        filter_dict = {}
        filter_countries_dict = {}
        if partition.countries:
            filter_dict = filter_expression_dict(countries=partition.countries)
            filter_countries_dict = {
                "filter_expression_countries": sorted(partition.countries),
            }

        rs_client.upload(
            record={
                "id": record_id,
                "type": geonames_record_type,
                "country": country,
                **filter_countries_dict,
                **filter_dict,
            },
            attachment=[_rs_geoname(g) for g in partition.geonames],
        )

    # Delete existing records for the country that weren't uploaded above.
    for record in rs_client.get_records():
        if (
            record.get("type") == geonames_record_type
            and record.get("country") == country
            and record["id"] not in uploaded_record_ids
        ):
            rs_client.delete_record(record["id"])


def _rs_geoname(geoname: Geoname) -> dict[str, Any]:
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
    if 1_000_000 <= value and value % 1_000_000 == 0:
        return f"{int(value / 1_000_000)}m"
    if 1_000 <= value and value % 1_000 == 0:
        return f"{int(value / 1_000)}k"
    return str(value)
