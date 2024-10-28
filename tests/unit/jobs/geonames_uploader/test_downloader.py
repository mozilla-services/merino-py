# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for downloader.py module."""

import csv
import pytest

from io import BufferedReader

from tempfile import NamedTemporaryFile
from zipfile import ZipFile

from merino.jobs.geonames_uploader.downloader import (
    GEONAME_COL_ID,
    GEONAME_COL_NAME,
    GEONAME_COL_LATITUDE,
    GEONAME_COL_LONGITUDE,
    GEONAME_COL_FEATURE_CLASS,
    GEONAME_COL_FEATURE_CODE,
    GEONAME_COL_COUNTRY_CODE,
    GEONAME_COL_ADMIN1_CODE,
    GEONAME_COL_POPULATION,
    MAX_GEONAME_COL,
    ALTERNATES_COL_GEONAME_ID,
    ALTERNATES_COL_ISO_LANGUAGE,
    ALTERNATES_COL_NAME,
    MAX_ALTERNATES_COL,
    DownloadMetrics,
    DownloadState,
    Geoname,
    GeonamesDownloader,
)


class GeonameAlternate:
    """Geoname alternate"""

    geoname_id: int
    iso_language: str
    name: str

    def __init__(
        self,
        geoname_id: int,
        iso_language: str,
        name: str,
    ):
        self.geoname_id = geoname_id
        self.iso_language = iso_language
        self.name = name


GEONAMES = [
    # Waterloo, AL
    Geoname(
        id=1,
        name="Waterloo",
        latitude="34.91814",
        longitude="-88.0642",
        feature_class="P",
        feature_code="PPL",
        country_code="US",
        admin1_code="AL",
        population=200,
    ),
    # AL
    Geoname(
        id=2,
        name="Alabama",
        latitude="32.75041",
        longitude="-86.75026",
        feature_class="A",
        feature_code="ADM1",
        country_code="US",
        admin1_code="AL",
        population=4530315,
    ),
    # Waterloo, IA
    Geoname(
        id=3,
        name="Waterloo",
        latitude="42.49276",
        longitude="-92.34296",
        feature_class="P",
        feature_code="PPLA2",
        country_code="US",
        admin1_code="IA",
        population=68460,
    ),
    # IA
    Geoname(
        id=4,
        name="Iowa",
        latitude="42.00027",
        longitude="-93.50049",
        feature_class="A",
        feature_code="ADM1",
        country_code="US",
        admin1_code="IA",
        population=2955010,
    ),
    # Waterloo Lake (not a city or region)
    Geoname(
        id=5,
        name="Waterloo Lake",
        latitude="31.25044",
        longitude="-99.25061",
        feature_class="H",
        feature_code="LK",
        country_code="US",
        admin1_code="TX",
        population=0,
    ),
    # New York City
    Geoname(
        id=6,
        name="New York City",
        latitude="40.71427",
        longitude="-74.00597",
        feature_class="P",
        feature_code="PPL",
        country_code="US",
        admin1_code="NY",
        population=8804190,
    ),
    # NY State
    Geoname(
        id=7,
        name="New York",
        latitude="43.00035",
        longitude="-75.4999",
        feature_class="A",
        feature_code="ADM1",
        country_code="US",
        admin1_code="NY",
        population=19274244,
    ),
]

ALTERNATES = [
    # Waterloo, AL
    GeonameAlternate(
        geoname_id=1,
        name="Waterloo",
        iso_language="en",
    ),
    # AL
    GeonameAlternate(
        geoname_id=2,
        name="AL",
        iso_language="abbr",
    ),
    GeonameAlternate(
        geoname_id=2,
        name="State of Alabama",
        iso_language="en",
    ),
    # Waterloo, IA
    GeonameAlternate(
        geoname_id=3,
        name="Waterloo",
        iso_language="en",
    ),
    # IA
    GeonameAlternate(
        geoname_id=4,
        name="IA",
        iso_language="abbr",
    ),
    GeonameAlternate(
        geoname_id=4,
        name="State of Iowa",
        iso_language="en",
    ),
    # Waterloo Lake
    GeonameAlternate(
        geoname_id=5,
        name="Waterloo",
        iso_language="en",
    ),
    GeonameAlternate(
        geoname_id=5,
        name="W. Lake",
        iso_language="en-US",
    ),
    # New York City
    GeonameAlternate(
        geoname_id=6,
        name="New York",
        iso_language="en",
    ),
    GeonameAlternate(
        geoname_id=6,
        name="NY",
        iso_language="abbr",
    ),
    GeonameAlternate(
        geoname_id=6,
        name="NYC",
        iso_language="abbr",
    ),
    GeonameAlternate(
        geoname_id=6,
        name="LGA",
        iso_language="iata",
    ),
    GeonameAlternate(
        geoname_id=6,
        name="Nueva York",
        iso_language="es",
    ),
    # NY State
    GeonameAlternate(
        geoname_id=7,
        name="NY",
        iso_language="abbr",
    ),
    GeonameAlternate(
        geoname_id=7,
        name="State of New York",
        iso_language="en",
    ),
    GeonameAlternate(
        geoname_id=7,
        name="Nueva York",
        iso_language="es",
    ),
]


class DownloaderTest:
    """Downloader test fixture"""

    geonames: BufferedReader
    alternates: BufferedReader

    def __init__(self) -> None:
        """Initialize test"""
        self.geonames = self.make_geonames_zip(GEONAMES)
        self.alternates = self.make_alternates_zip(ALTERNATES)

    def run(
        self,
        requests_mock,
        population_threshold: int,
        city_alternates_iso_languages: list[str],
        region_alternates_iso_languages: list[str],
        expected_geonames: list[Geoname],
        expected_metrics: DownloadMetrics,
    ) -> None:
        """Run test"""
        requests_mock.get("https://localhost/US.zip", body=self.geonames)
        requests_mock.get("https://localhost/alternates/US.zip", body=self.alternates)

        downloader = GeonamesDownloader(
            base_url="https://localhost",
            geonames_path="/{country_code}.zip",
            alternates_path="/alternates/{country_code}.zip",
            country_code="US",
            city_alternates_iso_languages=city_alternates_iso_languages,
            region_alternates_iso_languages=region_alternates_iso_languages,
            population_threshold=population_threshold,
        )
        state = downloader.download()

        self.assert_state(state, expected_geonames, expected_metrics)
        self.clean_up()

    def assert_state(
        self,
        actual_state: DownloadState,
        expected_geonames: list[Geoname],
        expected_metrics: DownloadMetrics,
    ) -> None:
        """Assert download state is equal to expected state"""
        state = DownloadState()
        state.geonames = expected_geonames
        state.geonames_by_id = {g.id: g for g in expected_geonames}
        state.metrics = expected_metrics
        assert actual_state == state

    def make_geonames_zip(self, geonames: list[Geoname]) -> BufferedReader:
        """Create a geonames zip file"""
        rows = []
        for g in geonames:
            row = [""] * (MAX_GEONAME_COL + 1)
            row[GEONAME_COL_ID] = str(g.id)
            row[GEONAME_COL_NAME] = g.name
            row[GEONAME_COL_LATITUDE] = g.latitude
            row[GEONAME_COL_LONGITUDE] = g.longitude
            row[GEONAME_COL_FEATURE_CLASS] = g.feature_class
            row[GEONAME_COL_FEATURE_CODE] = g.feature_code
            row[GEONAME_COL_COUNTRY_CODE] = g.country_code
            row[GEONAME_COL_ADMIN1_CODE] = g.admin1_code
            row[GEONAME_COL_POPULATION] = str(g.population)
            rows.append(row)
        return self.make_zip(rows, "US.txt")

    def make_alternates_zip(self, alternates: list[GeonameAlternate]) -> BufferedReader:
        """Create a geonames alternates zip file"""
        rows = []
        for a in alternates:
            row = [""] * (MAX_ALTERNATES_COL + 1)
            row[ALTERNATES_COL_GEONAME_ID] = str(a.geoname_id)
            row[ALTERNATES_COL_ISO_LANGUAGE] = a.iso_language
            row[ALTERNATES_COL_NAME] = a.name
            rows.append(row)
        return self.make_zip(rows, "US.txt")

    def make_zip(self, tsv_rows: list[list[str]], arcname: str) -> BufferedReader:
        """Create a zip file in a temporary directory with a single tsv item"""
        # Open a temporary tsv file and write the rows to it.
        tmp_tsv_file = NamedTemporaryFile(mode="wt", encoding="utf-8", delete_on_close=False)
        writer = csv.writer(tmp_tsv_file, dialect="excel-tab")
        for row in tsv_rows:
            writer.writerow(row)
        tmp_tsv_file.close()
        # Create a new zip file and add the tsv file to it.
        tmp_zip_file = NamedTemporaryFile(delete_on_close=False)
        zip_file = ZipFile(tmp_zip_file, mode="w")
        zip_file.write(tmp_tsv_file.name, arcname)
        # Close the zip file, reopen it, and return it.
        zip_file.close()
        return open(tmp_zip_file.name, mode="rb")

    def clean_up(self) -> None:
        """Tear down the test"""
        self.geonames.close()
        self.alternates.close()


@pytest.fixture()
def downloader_test() -> DownloaderTest:
    """Return downloader test fixture"""
    return DownloaderTest()


def test_all_populations_and_iso_languages(
    requests_mock,
    downloader_test: DownloaderTest,
):
    """Request geonames with populations > 0 and alternates of all ISO languages
    in the datset

    """
    downloader_test.run(
        requests_mock,
        population_threshold=1,
        city_alternates_iso_languages=["en", "es", "abbr", "iata"],
        region_alternates_iso_languages=["en", "es", "abbr"],
        expected_geonames=[
            Geoname(
                id=1,
                name="Waterloo",
                latitude="34.91814",
                longitude="-88.0642",
                feature_class="P",
                feature_code="PPL",
                country_code="US",
                admin1_code="AL",
                population=200,
                alternate_names=set(["waterloo"]),
            ),
            Geoname(
                id=2,
                name="Alabama",
                latitude="32.75041",
                longitude="-86.75026",
                feature_class="A",
                feature_code="ADM1",
                country_code="US",
                admin1_code="AL",
                population=4530315,
                alternate_names=set(["alabama", "state of alabama", "al"]),
            ),
            Geoname(
                id=3,
                name="Waterloo",
                latitude="42.49276",
                longitude="-92.34296",
                feature_class="P",
                feature_code="PPLA2",
                country_code="US",
                admin1_code="IA",
                population=68460,
                alternate_names=set(["waterloo"]),
            ),
            Geoname(
                id=4,
                name="Iowa",
                latitude="42.00027",
                longitude="-93.50049",
                feature_class="A",
                feature_code="ADM1",
                country_code="US",
                admin1_code="IA",
                population=2955010,
                alternate_names=set(["iowa", "state of iowa", "ia"]),
            ),
            Geoname(
                id=6,
                name="New York City",
                latitude="40.71427",
                longitude="-74.00597",
                feature_class="P",
                feature_code="PPL",
                country_code="US",
                admin1_code="NY",
                population=8804190,
                alternate_names=set(
                    ["new york city", "new york", "nueva york", "ny", "nyc", "lga"]
                ),
            ),
            Geoname(
                id=7,
                name="New York",
                latitude="43.00035",
                longitude="-75.4999",
                feature_class="A",
                feature_code="ADM1",
                country_code="US",
                admin1_code="NY",
                population=19274244,
                alternate_names=set(["new york", "state of new york", "nueva york", "ny"]),
            ),
        ],
        expected_metrics=DownloadMetrics(
            # No excluded cities or regions
            excluded_geonames_count=0,
            included_alternates_count=14,
        ),
    )


def test_one_million_population_and_all_iso_languages(
    requests_mock,
    downloader_test: DownloaderTest,
):
    """Request geonames with populations > one million and alternates of all ISO
    languages in the datset

    """
    downloader_test.run(
        requests_mock,
        population_threshold=1_000_000,
        city_alternates_iso_languages=["en", "es", "abbr", "iata"],
        region_alternates_iso_languages=["en", "es", "abbr"],
        expected_geonames=[
            Geoname(
                id=2,
                name="Alabama",
                latitude="32.75041",
                longitude="-86.75026",
                feature_class="A",
                feature_code="ADM1",
                country_code="US",
                admin1_code="AL",
                population=4530315,
                alternate_names=set(["alabama", "state of alabama", "al"]),
            ),
            Geoname(
                id=4,
                name="Iowa",
                latitude="42.00027",
                longitude="-93.50049",
                feature_class="A",
                feature_code="ADM1",
                country_code="US",
                admin1_code="IA",
                population=2955010,
                alternate_names=set(["iowa", "state of iowa", "ia"]),
            ),
            Geoname(
                id=6,
                name="New York City",
                latitude="40.71427",
                longitude="-74.00597",
                feature_class="P",
                feature_code="PPL",
                country_code="US",
                admin1_code="NY",
                population=8804190,
                alternate_names=set(
                    ["new york city", "new york", "nueva york", "ny", "nyc", "lga"]
                ),
            ),
            Geoname(
                id=7,
                name="New York",
                latitude="43.00035",
                longitude="-75.4999",
                feature_class="A",
                feature_code="ADM1",
                country_code="US",
                admin1_code="NY",
                population=19274244,
                alternate_names=set(["new york", "state of new york", "nueva york", "ny"]),
            ),
        ],
        expected_metrics=DownloadMetrics(
            # No Waterloo, AL or Waterloo, IA
            excluded_geonames_count=2,
            included_alternates_count=12,
        ),
    )


def test_one_million_population_and_en_only(
    requests_mock,
    downloader_test: DownloaderTest,
):
    """Request geonames with populations > one million, "en" and "abbr" alternates only"""
    downloader_test.run(
        requests_mock,
        population_threshold=1_000_000,
        city_alternates_iso_languages=["en"],
        region_alternates_iso_languages=["abbr"],
        expected_geonames=[
            Geoname(
                id=2,
                name="Alabama",
                latitude="32.75041",
                longitude="-86.75026",
                feature_class="A",
                feature_code="ADM1",
                country_code="US",
                admin1_code="AL",
                population=4530315,
                alternate_names=set(["alabama", "al"]),
            ),
            Geoname(
                id=4,
                name="Iowa",
                latitude="42.00027",
                longitude="-93.50049",
                feature_class="A",
                feature_code="ADM1",
                country_code="US",
                admin1_code="IA",
                population=2955010,
                alternate_names=set(["iowa", "ia"]),
            ),
            Geoname(
                id=6,
                name="New York City",
                latitude="40.71427",
                longitude="-74.00597",
                feature_class="P",
                feature_code="PPL",
                country_code="US",
                admin1_code="NY",
                population=8804190,
                alternate_names=set(["new york city", "new york"]),
            ),
            Geoname(
                id=7,
                name="New York",
                latitude="43.00035",
                longitude="-75.4999",
                feature_class="A",
                feature_code="ADM1",
                country_code="US",
                admin1_code="NY",
                population=19274244,
                alternate_names=set(["new york", "ny"]),
            ),
        ],
        expected_metrics=DownloadMetrics(
            # No Waterloo, AL or Waterloo, IA
            excluded_geonames_count=2,
            # Only "al", "ia", "new york" (city), and "ny" (state). Other
            # values in `altername_names` are lowercased versions of `name`.
            included_alternates_count=4,
        ),
    )
