"""The `upload alternates` command for the `geonames_uploader` job."""

import logging
from typing import Any, Tuple

from merino.jobs.utils.rs_client import RemoteSettingsClient, filter_expression_dict
from merino.jobs.geonames_uploader.downloader import download_alternates, GeonameAlternate


# This maps language codes to all locales that include them, for language codes
# that are not by themselves also locale codes. This is necessary because remote
# settings filter expressions can filter on locale but not language. Languages
# not listed here are assumed to also be valid locales.
LOCALES_BY_LANGUAGE = {
    "en": ["en-CA", "en-GB", "en-US", "en-ZA"],
}


logger = logging.getLogger(__name__)


def alternates_cmd(
    languages: set[str],
    alternates_record_type: str,
    alternates_url_format: str,
    country: str,
    geonames_record_type: str,
    rs_auth: str,
    rs_bucket: str,
    rs_collection: str,
    rs_dry_run: bool,
    rs_server: str,
):
    """Perform the `alternates` command, which uploads geonames alternates to
    remote settings.

    """
    rs_client = RemoteSettingsClient(
        auth=rs_auth,
        bucket=rs_bucket,
        collection=rs_collection,
        server=rs_server,
        dry_run=rs_dry_run,
    )

    # Get geonames records and existing alternates records for the country.
    geonames_records = []
    existing_alternates_records = []
    for record in rs_client.get_records():
        if record.get("type") == geonames_record_type and record.get("country") == country:
            geonames_records.append(record)
        elif (
            record.get("type") == alternates_record_type
            and record.get("country") == country
            and record.get("language") in languages
        ):
            existing_alternates_records.append(record)

    if not geonames_records:
        logger.info(f"No records for country '{country}' in remote settings, stopping")
        return

    # Download the attachments of the geonames records. Each attachment is a
    # list of geonames.
    record_and_geonames_tuples: list[Tuple[dict[str, Any], list[dict[int, Any]]]] = []
    all_geoname_ids: set[int] = set()
    for record in geonames_records:
        geonames = rs_client.download_attachment(record)
        record_and_geonames_tuples.append((record, geonames))
        all_geoname_ids |= set(g["id"] for g in geonames)

    # Download alternates from the geonames server.
    download = download_alternates(
        country=country,
        geoname_ids=all_geoname_ids,
        languages=languages,
        url_format=alternates_url_format,
    )

    # Create an alternates record for each language and geonames record.
    uploaded_record_ids = set()
    for lang in sorted(languages):
        for geonames_record, geonames in record_and_geonames_tuples:
            geonames_record_id = geonames_record["id"]
            geonames_by_id = {g["id"]: g for g in geonames}

            alts_by_geoname_id = {
                geoname_id: alt
                for geoname_id, alt in download.alternates_by_geoname_id_by_language.get(
                    lang, {}
                ).items()
                if geoname_id in geonames_by_id
            }
            if not alts_by_geoname_id:
                logger.warning(
                    f"No alternates for record '{geonames_record_id}' in language '{lang}'"
                )
                continue

            alts_record_id = f"{geonames_record_id}-{lang}"
            uploaded_record_ids.add(alts_record_id)

            # Build the filter expression. Include the same countries as the
            # geonames record.
            filter_countries = geonames_record.get("filter_expression_countries", [])

            # If the language code is a natural language and not "abbr"
            # (abbreviation) or "iata" (airport code), include a locales filter.
            filter_locales = []
            if lang not in ["abbr", "iata"]:
                filter_locales = [lang] + LOCALES_BY_LANGUAGE.get(lang, [])

            rs_client.upload(
                record={
                    "id": alts_record_id,
                    "type": alternates_record_type,
                    "country": country,
                    "language": lang,
                    **filter_expression_dict(countries=filter_countries, locales=filter_locales),
                },
                attachment={
                    "language": lang,
                    "alternates_by_geoname_id": [
                        [
                            geoname_id,
                            [_rs_alternate(alt, geonames_by_id[geoname_id]) for alt in alts],
                        ]
                        for geoname_id, alts in alts_by_geoname_id.items()
                    ],
                },
            )

    # Delete existing records for the country and languages that weren't
    # uploaded above.
    for r in existing_alternates_records:
        if r["id"] not in uploaded_record_ids:
            rs_client.delete_record(r["id"])


def _rs_alternate(
    alt: GeonameAlternate,
    geoname: dict[str, Any],
) -> str | dict[str, Any] | None:
    """Convert a `GeonameAlternate` to a dict that will be stored in an
    alternates attachment.

    """
    # The alternate is the name by itself if it doesn't have any metadata.
    if not alt.is_preferred and not alt.is_short:
        # The client automatically adds alternates without metadata for the
        # geoname's `name` and `ascii_name`, so save space in RS by excluding
        # the alternate if it's the same as them.
        if alt.name in [geoname.get("name"), geoname.get("ascii_name")]:
            return None

        return alt.name

    d: dict[str, Any] = {"name": alt.name}
    if alt.is_preferred:
        d["is_preferred"] = True
    if alt.is_short:
        d["is_short"] = True
    return d
