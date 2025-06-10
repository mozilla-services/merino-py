"""Geonames alternates helpers for the geonames-uploader command."""

from dataclasses import dataclass
import logging
from typing import Any, Iterable, Mapping, Tuple
import itertools

from merino.jobs.utils.rs_client import RecordData, RemoteSettingsClient, filter_expression_dict
from merino.jobs.geonames_uploader.downloader import download_alternates, GeonameAlternate

from merino.jobs.geonames_uploader.geonames import GeonamesRecord, RsGeoname


# Maps from Firefox locales to alternates languages in the geonames data.
ALTERNATES_LANGUAGES_BY_CLIENT_LOCALE = {
    "en-CA": ["en", "en-CA"],
    "en-GB": ["en", "en-GB"],
    "en-US": ["en"],
    "en-ZA": ["en"],
    "de": ["de"],
    "fr": ["fr"],
    "it": ["it"],
    "pl": ["pl"],
}

# Geonames pseudo-language codes for which we should create alternates records.
# There are others than the ones here but typically we shouldn't be using them.
PSEUDO_LANGUAGES = [
    "abbr",  # abbreviations
    "iata",  # airport codes
]


# A representation of a `GeonameAlternate` appropriate for including in an
# alternates attachment. Alternates with `is_preferred` or `is_short` set to
# `True` will be a dict. Others will be a string.
RsAlternate = dict[str, Any] | str


logger = logging.getLogger(__name__)


@dataclass
class AlternatesUpload:
    """The result of a successful alternates records upload."""

    uploaded_count: int = 0
    not_uploaded_count: int = 0
    deleted_count: int = 0


def upload_alternates(
    alternates_record_type: str,
    alternates_url_format: str,
    country: str,
    existing_alternates_records_by_id: Mapping[str, RecordData],
    force_reupload: bool,
    geonames_record_type: str,
    geonames_records: list[GeonamesRecord],
    locales_by_country: Mapping[str, Iterable[str]],
    rs_client: RemoteSettingsClient,
    alternates_languages_by_client_locale: Mapping[
        str, Iterable[str]
    ] = ALTERNATES_LANGUAGES_BY_CLIENT_LOCALE,
) -> AlternatesUpload:
    """Download alternates from the geonames server for a given country and
    upload alternates records to remote settings.

    """
    logger.info(f"Uploading alternates records for country '{country}'")

    upload = AlternatesUpload()

    # If there are no geonames records for the country, consider all its
    # alternates records as unused and delete them. Then we're done.
    if not geonames_records:
        logger.info(f"No geonames records for country '{country}'")
        for record_id in existing_alternates_records_by_id.keys():
            rs_client.delete_record(record_id)
        upload.deleted_count = len(existing_alternates_records_by_id)
        return upload

    # Build a set of all geoname IDs.
    all_geoname_ids = set(
        itertools.chain.from_iterable((g["id"] for g in r.geonames) for r in geonames_records)
    )

    # Build a set of all alternates languages and an augmented version of
    # `locales_by_country` that maps from locales to alternates languages.
    all_langs: set[str] = set(PSEUDO_LANGUAGES)
    langs_by_locale_by_country: dict[str, dict[str, set[str]]] = {}
    for client_country, locales in locales_by_country.items():
        for locale in locales:
            langs = alternates_languages_by_client_locale.get(locale)
            if not langs:
                raise ValueError(
                    f"Client locale '{locale}' not mapped to any alternates languages. "
                    "Please add an entry for it!"
                )
            for lang in langs:
                all_langs.add(lang)
                langs_by_locale_by_country.setdefault(client_country, {}).setdefault(
                    locale, set()
                ).add(lang)

    # Download alternates from the geonames server.
    download = download_alternates(
        country=country,
        geoname_ids=all_geoname_ids,
        languages=all_langs,
        url_format=alternates_url_format,
    )

    # For each geonames record and language, create (potentially) an alternates
    # record.
    final_record_ids = set()
    for geonames_record in geonames_records:
        geonames_record_id = geonames_record.data["id"]
        geonames_by_id = {g["id"]: g for g in geonames_record.geonames}
        client_countries = geonames_record.data.get("client_countries", [])

        # Build a map from alternates languages to client locales for the
        # locales that are relevant to the client countries in the geonames
        # record. If the record doesn't have any client countries, then the map
        # will contain all supported languages and locales. Always include the
        # pseudo-languages since they're locale agnostic.
        locales_by_lang: dict[str, set[str]] = {lang: set() for lang in PSEUDO_LANGUAGES}
        for lang_country, langs_by_locale in langs_by_locale_by_country.items():
            if not client_countries or lang_country in client_countries:
                for locale, langs in langs_by_locale.items():
                    for lang in langs:
                        locales_by_lang.setdefault(lang, set()).add(locale)

        # For each language, create (potentially) an alternates record.
        for lang, locales in sorted(list(locales_by_lang.items()), key=lambda t: t[0]):
            # Collect the alternates for the geonames in the geonames record.
            alts_by_geoname_id = {
                geoname_id: alt
                for geoname_id, alt in download.alternates_by_geoname_id_by_language.get(
                    lang, {}
                ).items()
                if geoname_id in geonames_by_id
            }
            if not alts_by_geoname_id:
                # No alternates for this country and language.
                logger.info(
                    f"{geonames_record_id}: No alternates for country '{country}' and language '{lang}'"
                )
                continue

            # Build the list of tuples of geoname IDs and alternates for the
            # attachment. Keep in mind that `_rs_alternate` may return None.
            rs_geoname_and_alts_lists = _rs_alternates_list(
                [
                    (geonames_by_id[geoname_id], alts)
                    for geoname_id, alts in alts_by_geoname_id.items()
                ]
            )
            if not rs_geoname_and_alts_lists:
                # There are alternates for this country and language, but
                # they're all the same as their geonames' names or ASCII names,
                # so no alternates record is necessary.
                logger.info(
                    f"{geonames_record_id}: Alternates unnecessary for country '{country}' and language '{lang}'"
                )
                continue

            alts_record_id = f"{geonames_record_id}-{lang}"
            final_record_ids.add(alts_record_id)

            record = {
                "id": alts_record_id,
                "type": alternates_record_type,
                "country": country,
                "language": lang,
                **filter_expression_dict(locales=locales),
            }

            existing_alts_record = existing_alternates_records_by_id.get(alts_record_id)
            force_record = force_reupload or bool(
                existing_alts_record
                and record != {k: existing_alts_record.get(k) for k, v in record.items()}
            )

            uploaded = rs_client.upload(
                record=record,
                attachment={
                    "language": lang,
                    "alternates_by_geoname_id": rs_geoname_and_alts_lists,
                },
                existing_record=existing_alts_record,
                force_reupload=force_record,
            )

            if uploaded:
                upload.uploaded_count += 1
            else:
                upload.not_uploaded_count += 1

    # Delete existing records for the country and languages that weren't
    # uploaded above.
    for record_id in existing_alternates_records_by_id.keys():
        if record_id not in final_record_ids:
            rs_client.delete_record(record_id)
            upload.deleted_count += 1

    return upload


def _rs_alternates_list(
    rs_geoname_and_alts_tuples: list[Tuple[RsGeoname, list[GeonameAlternate]]],
) -> list[Tuple[int, list[RsAlternate]]]:
    """Convert a list of `(rs_geoname, [GeonameAlternate])` tuples to a list of
    `(geoname_id, [rs_alternate])` tuples appropriate for including in an
    alternates attachment as `alternates_by_geoname_id`.

    """
    geoname_id_and_rs_alts_tuples: list[Tuple[int, list[RsAlternate]]] = []
    for rs_geoname, alts in rs_geoname_and_alts_tuples:
        rs_alts = []
        for alt in alts:
            rs_alt = _rs_alternate(alt, rs_geoname)
            if rs_alt:
                rs_alts.append(rs_alt)
        if rs_alts:
            geoname_id_and_rs_alts_tuples.append((rs_geoname["id"], rs_alts))
    return geoname_id_and_rs_alts_tuples


def _rs_alternate(
    alt: GeonameAlternate,
    geoname: RsGeoname,
) -> RsAlternate | None:
    """Convert a `GeonameAlternate` to a value appropriate for including in an
    alternates attachment. Return `None` if the alternate should be excluded.

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
