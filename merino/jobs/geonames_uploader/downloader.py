"""Utilities for downloading and processing data from GeoNames. GeoNames is an
open-source database of geographical place data worldwide, including cities,
regions, and countries [1]. See technical documentation at [2].

[1] https://www.geonames.org/
[2] https://download.geonames.org/export/dump/readme.txt

"""

import logging
from typing import Any, Callable

import csv
import requests

from merino.jobs.geonames_uploader.tempzipfile import TempZipFile

logger = logging.getLogger(__name__)


# Column indexes in the `geoname` table described in the GeoNames documentation.
GEONAME_COL_ID = 0
GEONAME_COL_NAME = 1
GEONAME_COL_ASCII_NAME = 2
GEONAME_COL_LATITUDE = 4
GEONAME_COL_LONGITUDE = 5
GEONAME_COL_FEATURE_CLASS = 6
GEONAME_COL_FEATURE_CODE = 7
GEONAME_COL_COUNTRY_CODE = 8
GEONAME_COL_ADMIN1_CODE = 10
GEONAME_COL_ADMIN2_CODE = 11
GEONAME_COL_ADMIN3_CODE = 12
GEONAME_COL_ADMIN4_CODE = 13
GEONAME_COL_POPULATION = 14
MAX_GEONAME_COL = GEONAME_COL_POPULATION

# Column indexes in the `alternate names` table described in the GeoNames
# documentation.
ALTERNATES_COL_GEONAME_ID = 1
ALTERNATES_COL_ISO_LANGUAGE = 2
ALTERNATES_COL_NAME = 3
ALTERNATES_COL_IS_PREFERRED = 4
ALTERNATES_COL_IS_SHORT = 5
MAX_ALTERNATES_COL = ALTERNATES_COL_IS_SHORT

FEATURE_CLASS_ADMIN_DIVISION = "A"
FEATURE_CLASS_CITY = "P"


class Geoname:
    """A geoname is a representation of a single place like a city, state, or
    region. An instance of this class corresponds to a single row in the
    `geoname` table described in the GeoNames documentation (see link above).

    """

    id: int
    name: str
    ascii_name: str
    latitude: str | None
    longitude: str | None
    feature_class: str
    feature_code: str
    country_code: str
    admin1_code: str | None
    admin2_code: str | None
    admin3_code: str | None
    admin4_code: str | None
    population: int | None

    def __init__(
        self,
        id: int,
        name: str,
        ascii_name: str,
        latitude: str | None,
        longitude: str | None,
        feature_class: str,
        feature_code: str,
        country_code: str,
        population: int | None,
        admin1_code: str | None = None,
        admin2_code: str | None = None,
        admin3_code: str | None = None,
        admin4_code: str | None = None,
    ):
        """Initialize the geoname."""
        self.id = id
        self.name = name
        self.ascii_name = ascii_name
        self.latitude = latitude
        self.longitude = longitude
        self.feature_class = feature_class
        self.feature_code = feature_code
        self.country_code = country_code
        self.population = population
        self.admin1_code = admin1_code
        self.admin2_code = admin2_code
        self.admin3_code = admin3_code
        self.admin4_code = admin4_code

    def __repr__(self) -> str:
        return str(vars(self))

    def __eq__(self, other) -> bool:
        return isinstance(other, Geoname) and vars(self) == vars(other)


class GeonameAlternate:
    """An alternate name for a geoname selected during the download process. A
    single geoname can have many alternate names since a place can have many
    different variations of its name. Alternate names can also include
    translations of the geoname's name into different languages.

    """

    name: str
    is_preferred: bool
    is_short: bool

    def __init__(self, name: str, is_preferred: bool = False, is_short: bool = False):
        self.name = name
        self.is_preferred = is_preferred
        self.is_short = is_short

    def __repr__(self) -> str:
        return str(vars(self))

    def __eq__(self, other) -> bool:
        return isinstance(other, GeonameAlternate) and vars(self) == vars(other)


class GeonamesDownload:
    """The result of a successful geonames download. When complete, `geonames`
    will be the downloaded geonames.

    """

    population_threshold: int
    geonames: list[Geoname]

    def __init__(
        self,
        population_threshold: int,
        geonames: list[Geoname] | None = None,
    ):
        """Initialize the download."""
        self.population_threshold = population_threshold
        self.geonames = geonames or []

    def _process_line(self, line: list[str]) -> None:
        geoname_id = int(line[GEONAME_COL_ID])
        latitude = line[GEONAME_COL_LATITUDE]
        longitude = line[GEONAME_COL_LONGITUDE]
        feature_class = line[GEONAME_COL_FEATURE_CLASS]
        feature_code = line[GEONAME_COL_FEATURE_CODE]
        population = int(line[GEONAME_COL_POPULATION])
        is_city = feature_class == FEATURE_CLASS_CITY
        is_admin_division = feature_class == FEATURE_CLASS_ADMIN_DIVISION
        if (is_city or is_admin_division) and self.population_threshold <= population:
            self.geonames.append(
                Geoname(
                    id=geoname_id,
                    name=line[GEONAME_COL_NAME],
                    ascii_name=line[GEONAME_COL_ASCII_NAME],
                    latitude=latitude or None,
                    longitude=longitude or None,
                    feature_class=feature_class,
                    feature_code=feature_code,
                    country_code=line[GEONAME_COL_COUNTRY_CODE],
                    admin1_code=line[GEONAME_COL_ADMIN1_CODE] or None,
                    admin2_code=line[GEONAME_COL_ADMIN2_CODE] or None,
                    admin3_code=line[GEONAME_COL_ADMIN3_CODE] or None,
                    admin4_code=line[GEONAME_COL_ADMIN4_CODE] or None,
                    population=population or None,
                )
            )

    def __repr__(self) -> str:
        return str(vars(self))

    def __eq__(self, other) -> bool:
        return isinstance(other, GeonamesDownload) and vars(self) == vars(other)


def download_geonames(
    country: str,
    population_threshold: int,
    url_format: str,
) -> GeonamesDownload:
    """Download geonames for a given country.

    `country` is an ISO-3166 uppercase two-letter code that indicates the
    country of the geonames to download, e.g., "US".

    `population_threshold` specifies how large a geoname's population must
    be for it to be included in the output. Geonames with populations at
    least this large will be included.

    `url_format` is the URL on the GeoNames server of the country-specific
    geonames zip file. It should be a format string that includes a `country`
    variable.

    """
    dl = GeonamesDownload(population_threshold=population_threshold)
    _download(url_format, country, dl, dl._process_line)
    return dl


class AlternatesDownload:
    """The result of a successful geonames alternates download. When complete,
    `alternates_by_geoname_id_by_language` will be the download alternates.

    """

    languages: set[str]
    geonames_ids: set[int] | None
    alternates_by_geoname_id_by_language: dict[str, dict[int, list[GeonameAlternate]]]

    def __init__(
        self,
        languages: set[str],
        geoname_ids: set[int] | None = None,
        alternates_by_geoname_id_by_language: dict[str, dict[int, list[GeonameAlternate]]]
        | None = None,
    ):
        """Initialize the download. Alternates will be filtered to languages in
        `languages` and geonames in `geoname_ids`.

        """
        self.languages = languages
        self.geoname_ids = geoname_ids
        self.alternates_by_geoname_id_by_language = alternates_by_geoname_id_by_language or {}

    def _process_line(self, line: list[str]) -> None:
        geoname_id = int(line[ALTERNATES_COL_GEONAME_ID])
        lang = line[ALTERNATES_COL_ISO_LANGUAGE]
        name = line[ALTERNATES_COL_NAME]
        is_preferred = line[ALTERNATES_COL_IS_PREFERRED]
        is_short = line[ALTERNATES_COL_IS_SHORT]
        if (self.geoname_ids is None or geoname_id in self.geoname_ids) and lang in self.languages:
            self._add_alternate(geoname_id, lang, name, is_preferred, is_short)

    def _add_alternate(
        self,
        geoname_id: int,
        language: str,
        name: str,
        is_preferred: str,
        is_short: str,
    ) -> None:
        alts_by_geoname_id = self.alternates_by_geoname_id_by_language.setdefault(language, {})
        alts = alts_by_geoname_id.setdefault(geoname_id, [])
        alts.append(GeonameAlternate(name, is_preferred == "1", is_short == "1"))

    def __repr__(self) -> str:
        return str(vars(self))

    def __eq__(self, other) -> bool:
        return isinstance(other, AlternatesDownload) and vars(self) == vars(other)


def download_alternates(
    country: str,
    languages: set[str],
    url_format: str,
    geoname_ids: set[int] | None = None,
) -> AlternatesDownload:
    """Download alternates for a given country.

    `country` is an ISO-3166 uppercase two-letter code that indicates the
    country of the geonames to download, e.g., "US".

    `url_format` is the URL on the GeoNames server of the country-specific
    alternates zip file. It should be a format string that includes a `country`
    variable.

    Alternates will be filtered to geonames with IDs in `geoname_ids` and
    languages in `languages`. Each str in `languages` should be either a
    lowercase ISO 639 language code ("en", "de", "fr") or one of the other
    pseudo-language categories supported by GeoNames like abbreviations ("abbr")
    and airport codes ("iata", "icao", "faac") (see documentation link above).

    """
    dl = AlternatesDownload(languages=languages, geoname_ids=geoname_ids)
    _download(url_format, country, dl, dl._process_line)
    return dl


def _download(
    url_format: str,
    country: str,
    state: Any,
    process_line: Callable[[list[str]], None],
) -> None:
    url = url_format.format(country=country)
    logger.info(f"Sending request: {url}")
    resp = requests.get(url, stream=True)  # nosec
    resp.raise_for_status()
    content_len = resp.headers.get("content-length", "???")
    logger.info(f"Downloading {url} ({content_len} bytes)...")
    with TempZipFile(resp.raw) as zip_file:
        txt_filename = f"{country}.txt"
        logger.info(f"Extracting {txt_filename} from {url}...")
        txt_path = zip_file.extract(txt_filename)
        logger.info(f"Opening {txt_filename} from {url}...")
        with open(txt_path, newline="", encoding="utf-8-sig") as txt_file:
            reader = csv.reader(txt_file, dialect="excel-tab")
            for line in reader:
                process_line(line)
