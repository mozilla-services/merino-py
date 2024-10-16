"""Utilities for downloading and processing data from GeoNames. GeoNames is an
open-source geographical database of place names worldwide, including cities,
regions, and countries [1]. See technical documentation at [2].

[1] https://www.geonames.org/
[2] https://download.geonames.org/export/dump/readme.txt

"""

import logging
from typing import Any, Callable

import csv
import requests
from urllib.parse import urljoin

from merino.jobs.geonames_uploader.tempzipfile import TempZipFile

logger = logging.getLogger(__name__)


# Column indexes in the `geoname` table described in the GeoNames documentation.
GEONAME_COL_ID = 0
GEONAME_COL_NAME = 1
GEONAME_COL_FEATURE_CLASS = 6
GEONAME_COL_FEATURE_CODE = 7
GEONAME_COL_COUNTRY_CODE = 8
GEONAME_COL_ADMIN1_CODE = 10
GEONAME_COL_POPULATION = 14
MAX_GEONAME_COL = GEONAME_COL_POPULATION

# Column indexes in the `alternate names` table described in the GeoNames
# documentation.
ALTERNATES_COL_GEONAME_ID = 1
ALTERNATES_COL_ISO_LANGUAGE = 2
ALTERNATES_COL_NAME = 3
MAX_ALTERNATES_COL = ALTERNATES_COL_NAME

FEATURE_CLASS_CITY = "P"
FEATURE_CLASS_REGION = "A"
FEATURE_CODE_REGION = "ADM1"


class Geoname:
    """A geoname is a representation of a single place like a city, state, or
    region. An instance of this class corresponds to a single row in the
    `geoname` table described in the GeoNames documentation (see link above).

    This class also includes a set of `alternate_names` containing lowercased
    versions of all the geoname's alternate names selected during the download
    process. A single geoname can have many alternate names since a place can
    have many different variations of its name. Alternate names can also include
    translations of the geoname's name into different languages.

    """

    id: str
    name: str
    feature_class: str
    feature_code: str
    country_code: str
    admin1_code: str
    population: int
    alternate_names: set[str]

    def __init__(
        self,
        id: str,
        name: str,
        feature_class: str,
        feature_code: str,
        country_code: str,
        admin1_code: str,
        population: int,
        alternate_names: set[str] | None = None,
    ):
        """Initialize the geoname."""
        self.id = id
        self.name = name
        self.feature_class = feature_class
        self.feature_code = feature_code
        self.country_code = country_code
        self.admin1_code = admin1_code
        self.population = population
        self.alternate_names = alternate_names or set([])
        # Always make sure `name` is present as an alternate name. The client
        # implementation relies on this.
        self.alternate_names.add(name.casefold())

    def to_json_serializable(self) -> dict[str, Any]:
        """Return a `dict` version of the geoname that is JSON serializable."""
        self_dict = vars(self)
        for k, v in self_dict.items():
            if isinstance(v, set):
                self_dict[k] = list(v)
        return self_dict

    def __repr__(self) -> str:
        return str(vars(self))

    def __eq__(self, other) -> bool:
        return isinstance(other, Geoname) and vars(self) == vars(other)


class DownloadMetrics:
    """Download metrics useful for logging."""

    excluded_geonames_count: int
    included_alternates_count: int

    def __init__(
        self,
        excluded_geonames_count: int = 0,
        included_alternates_count: int = 0,
    ):
        self.excluded_geonames_count = excluded_geonames_count
        self.included_alternates_count = included_alternates_count

    def __repr__(self) -> str:
        return str(vars(self))

    def __eq__(self, other) -> bool:
        return isinstance(other, DownloadMetrics) and vars(self) == vars(other)


class DownloadState:
    """The result of a successful GeoNames download."""

    geonames: list[Geoname]
    geonames_by_id: dict[str, Geoname]
    metrics: DownloadMetrics

    def __init__(
        self,
        geonames: list[Geoname] | None = None,
        geonames_by_id: dict[str, Geoname] | None = None,
        metrics: DownloadMetrics | None = None,
    ) -> None:
        """Initialize the state."""
        self.geonames = geonames or []
        self.geonames_by_id = geonames_by_id or {}
        self.metrics = metrics or DownloadMetrics()

    def __repr__(self) -> str:
        return str(vars(self))

    def __eq__(self, other) -> bool:
        return isinstance(other, DownloadState) and vars(self) == vars(other)


class GeonamesDownloader:
    """Downloads geonames and alternates for the cities and regions of a given
    country from the GeoNames server.

    Usage:

    downloader = GeonamesDownloader(
        base_url="https://download.geonames.org/",
        geonames_path="/export/dump/{country_code}.zip",
        alternates_path="/export/dump/alternatenames/{country_code}.zip",
        country_code="US",
        alternates_iso_languages=["en", "en-US", "iata", "icao", "faac", "abbr"],
        population_threshold=100_000,
    )
    state = downloader.download()
    for geoname in state.geonames:
        print(geoname)

    """

    base_url: str
    geonames_path: str
    alternates_path: str
    country_code: str
    population_threshold: int
    alternates_iso_languages: set[str]

    def __init__(
        self,
        base_url: str,
        geonames_path: str,
        alternates_path: str,
        country_code: str,
        population_threshold: int,
        alternates_iso_languages: list[str],
    ):
        """Initialize the downloader for a given country.

        `base_url` is the base URL of the GeoNames server.

        `geonames_path` and `alternates_path` are the full paths on the server
        of country-specific geonames and alternates. It's assumed that both
        paths are format strings that include a `country_code` variable.

        `country_code` is an ISO-3166 uppercase two-letter code that indicates
        the country of the geonames to download, e.g., "US".

        `population_threshold` specifies how large a geoname's population must
        be for it to be included in the output. Geonames with populations at
        least this large will be included.

        `alternates_iso_languages` specifies which alternates of selected
        geonames to include in the output. Alternates are categorized by
        language, like "en" and "en-US", plus a few other categories like
        abbreviations ("abbr") and airport codes ("iata", "icao", "faac") (see
        documentation link above). `alternates_iso_languages` should contain all
        such categories you want to include in the output.

        """
        self.base_url = base_url
        self.geonames_path = geonames_path
        self.alternates_path = alternates_path
        self.country_code = country_code
        self.population_threshold = population_threshold
        self.geonames = None
        self.geonames_ids = None
        self.alternates_iso_languages = set(alternates_iso_languages)

    def download(self) -> DownloadState:
        """Download selected geonames and alternates."""
        state = self.download_geonames()
        total_geonames_count = len(state.geonames) + state.metrics.excluded_geonames_count
        logger.info(f"{len(state.geonames)} of {total_geonames_count} eligible geonames selected")
        self.download_alternates(state)
        logger.info(f"{state.metrics.included_alternates_count} alternates selected")
        return state

    def download_geonames(self) -> DownloadState:
        """Download geonames only."""
        url = urljoin(self.base_url, self.geonames_path.format(country_code=self.country_code))
        return self._download(url, DownloadState(), self._process_geoname)

    def download_alternates(self, state: DownloadState) -> DownloadState:
        """Download alternates only."""
        url = urljoin(self.base_url, self.alternates_path.format(country_code=self.country_code))
        return self._download(url, state, self._process_alternate)

    def _process_geoname(self, line: list[str], state: DownloadState) -> None:
        geoname_id = line[GEONAME_COL_ID]
        feature_class = line[GEONAME_COL_FEATURE_CLASS]
        feature_code = line[GEONAME_COL_FEATURE_CODE]
        population = int(line[GEONAME_COL_POPULATION])
        is_city = feature_class == FEATURE_CLASS_CITY
        is_region = feature_class == FEATURE_CLASS_REGION and feature_code == FEATURE_CODE_REGION
        if is_city or is_region:
            if population >= self.population_threshold:
                geoname = Geoname(
                    id=geoname_id,
                    name=line[GEONAME_COL_NAME],
                    feature_class=feature_class,
                    feature_code=feature_code,
                    country_code=line[GEONAME_COL_COUNTRY_CODE],
                    admin1_code=line[GEONAME_COL_ADMIN1_CODE],
                    population=population,
                )
                state.geonames.append(geoname)
                state.geonames_by_id[geoname_id] = geoname
            else:
                state.metrics.excluded_geonames_count += 1

    def _process_alternate(self, line: list[str], state: DownloadState) -> None:
        geoname_id = line[ALTERNATES_COL_GEONAME_ID]
        iso_language = line[ALTERNATES_COL_ISO_LANGUAGE]
        name = line[ALTERNATES_COL_NAME]
        geoname = state.geonames_by_id.get(geoname_id, None)
        if geoname and iso_language in self.alternates_iso_languages:
            geoname.alternate_names.add(name.casefold())
            state.metrics.included_alternates_count += 1

    def _download(
        self,
        url: str,
        state: DownloadState,
        process_item: Callable[[list[str], DownloadState], None],
    ) -> DownloadState:
        logger.info(f"Sending request: {url}")
        resp = requests.get(url, stream=True)  # nosec
        resp.raise_for_status()
        content_len = resp.headers.get("content-length", "???")
        logger.info(f"Downloading {url} ({content_len} bytes)...")
        with TempZipFile(resp.raw) as zip_file:
            txt_filename = f"{self.country_code}.txt"
            logger.info(f"Extracting {txt_filename} from {url}...")
            txt_path = zip_file.extract(txt_filename)
            logger.info(f"Opening {txt_filename} from {url}...")
            with open(txt_path, newline="", encoding="utf-8-sig") as txt_file:
                reader = csv.reader(txt_file, dialect="excel-tab")
                for line in reader:
                    process_item(line, state)
        return state
