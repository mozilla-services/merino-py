# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

#XXXadw update comments/docstrings here and test_downloader etc.

"""Unit tests for downloader.py module."""

import csv
import pytest

from io import BufferedReader

from copy import deepcopy
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
    GEONAME_COL_ADMIN2_CODE,
    GEONAME_COL_ADMIN3_CODE,
    GEONAME_COL_ADMIN4_CODE,
    GEONAME_COL_POPULATION,
    MAX_GEONAME_COL,
    ALTERNATES_COL_GEONAME_ID,
    ALTERNATES_COL_ISO_LANGUAGE,
    ALTERNATES_COL_NAME,
    MAX_ALTERNATES_COL,
    Geoname,
)

SERVER_DATA = {
    "base_url": "https://geonames",
    "geonames_path": "/{country_code}.zip",
    "alternates_path": "/alternates/{country_code}.zip",
}

# Waterloo, AL
GEONAME_WATERLOO_AL = Geoname(
    id=4096497,
    name="Waterloo",
    latitude="34.91814",
    longitude="-88.0642",
    feature_class="P",
    feature_code="PPL",
    country_code="US",
    admin1_code="AL",
    admin2_code="077",
    population=200,
    alternates_by_iso_language={
        "en": ["Waterloo"],
    },
)

# AL
GEONAME_AL = Geoname(
    id=4829764,
    name="Alabama",
    latitude="32.75041",
    longitude="-86.75026",
    feature_class="A",
    feature_code="ADM1",
    country_code="US",
    admin1_code="AL",
    population=4530315,
    alternates_by_iso_language={
        "abbr": ["AL"],
        "en": ["State of Alabama"],
    },
)

# Waterloo, IA
GEONAME_WATERLOO_IA = Geoname(
    id=4880889,
    name="Waterloo",
    latitude="42.49276",
    longitude="-92.34296",
    feature_class="P",
    feature_code="PPLA2",
    country_code="US",
    admin1_code="IA",
    admin2_code="013",
    admin3_code="94597",
    admin4_code="ABC",
    population=68460,
    alternates_by_iso_language={
        "en": ["Waterloo"],
        "es": ["Waterloo"],
    },
)

# IA
GEONAME_IA = Geoname(
    id=4862182,
    name="Iowa",
    latitude="42.00027",
    longitude="-93.50049",
    feature_class="A",
    feature_code="ADM1",
    country_code="US",
    admin1_code="IA",
    population=2955010,
    alternates_by_iso_language={
        "abbr": ["IA"],
        "en": ["State of Iowa"],
    },
)

# New York City
GEONAME_NYC = Geoname(
    id=5128581,
    name="New York City",
    latitude="40.71427",
    longitude="-74.00597",
    feature_class="P",
    feature_code="PPL",
    country_code="US",
    admin1_code="NY",
    population=8804190,
    alternates_by_iso_language={
        "abbr": ["NY", "NYC"],
        "en": ["New York", "Da Big Apple Baby"],
        "es": ["Nueva York"],
        "iata": ["LGA"],
    },
)

# NY State
GEONAME_NY_STATE = Geoname(
    id=5128638,
    name="New York",
    latitude="43.00035",
    longitude="-75.4999",
    feature_class="A",
    feature_code="ADM1",
    country_code="US",
    admin1_code="NY",
    population=19274244,
    alternates_by_iso_language={
        "abbr": ["NY"],
        "en": ["New York", "State of New York"],
        "es": ["Nueva York"],
    },
)

# Geonames that will populate the mock GeoNames files
GEONAMES = [
    GEONAME_WATERLOO_AL,
    GEONAME_AL,
    GEONAME_WATERLOO_IA,
    GEONAME_IA,
    GEONAME_NYC,
    GEONAME_NY_STATE,

#     # Waterloo Lake (not a city or region, should be excluded)
#     Geoname(
#         id=5,
#         name="Waterloo Lake",
#         latitude="31.25044",
#         longitude="-99.25061",
#         feature_class="H",
#         feature_code="LK",
#         country_code="US",
#         admin1_code="TX",
#         population=0,
#         alternates_by_iso_language={
#             "en": ["Waterloo", "W. Lake"],
#         },
#     ),
]

# # Alternates that will populate the mock GeoNames files
# ALTERNATES = {
#     # Waterloo, AL
#     4096497: {
#         "en": ["Waterloo"],
#     },
#     # AL
#     4829764: {
#         "abbr": ["AL"],
#         "en": ["State of Alabama"],
#     },
#     # Waterloo, IA -- Give it two alternates with the same `name` but different
#     # `iso_language` values to make sure only one of them is in the output.
#     4880889: {
#         "en": ["Waterloo"],
#         "es": ["Waterloo"],
#     },
#     # IA
#     4862182: {
#         "abbr": ["IA"],
#         "en": ["State of Iowa"],
#     },
#     # Waterloo Lake
#     5: {
#         "en": ["Waterloo", "W. Lake"],
#     },
#     # New York City
#     5128581: {
#         "abbr": ["NY", "NYC"],
#         "en": ["New York", "Da Big Apple Baby"],
#         "es": ["Nueva York"],
#         "iata": ["LGA"],
#     },
#     # NY State
#     5128638: {
#         "abbr": ["NY"],
#         "en": ["New York", "State of New York"],
#         "es": ["Nueva York"],
#     },
# }


class DownloaderFixture:
    """Downloader test fixture"""

    geonames: BufferedReader
    alternates: BufferedReader

#     def __init__(self) -> None:
    def __init__(self, requests_mock) -> None:
#     def __init__(self, requests_mock, base_url: str = "https://localhost") -> None:
        """Initialize test"""
        print(f"*******XXXadw DownloaderFixture {requests_mock}")
        self.geonames = self.make_geonames_zip(GEONAMES)
#         self.alternates = self.make_alternates_zip(ALTERNATES)
        self.alternates = self.make_alternates_zip(GEONAMES)

#         requests_mock.get("https://localhost/US.zip", body=self.geonames)
#         requests_mock.get("https://localhost/alternates/US.zip", body=self.alternates)

#         requests_mock.get(f"{base_url}/US.zip", body=self.geonames)
#         requests_mock.get(f"{base_url}/alternates/US.zip", body=self.alternates)

#         requests_mock.get("https://geonames/US.zip", body=self.geonames)
#         requests_mock.get("https://geonames/alternates/US.zip", body=self.alternates)

        geonames_url = SERVER_DATA["base_url"] + SERVER_DATA["geonames_path"].format(country_code="US")
        alternates_url = SERVER_DATA["base_url"] + SERVER_DATA["alternates_path"].format(country_code="US")

        print(f"*******XXXadw DownloaderFixture geonames_url={geonames_url}")
        print(f"*******XXXadw DownloaderFixture alternates_url={alternates_url}")

#         requests_mock.get("https://geonames/US.zip", body=self.geonames)
#         requests_mock.get("https://geonames/alternates/US.zip", body=self.alternates)
        requests_mock.get(geonames_url, body=self.geonames)
        requests_mock.get(alternates_url, body=self.alternates)


#     def set_up(self, requests_mock) -> None:
#         """XXXadw"""
#         requests_mock.get("https://localhost/US.zip", body=self.geonames)
#         requests_mock.get("https://localhost/alternates/US.zip", body=self.alternates)

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
            row[GEONAME_COL_ADMIN2_CODE] = g.admin2_code
            row[GEONAME_COL_ADMIN3_CODE] = g.admin3_code
            row[GEONAME_COL_ADMIN4_CODE] = g.admin4_code
            row[GEONAME_COL_POPULATION] = str(g.population)
            rows.append(row)
        return self.make_zip(rows, "US.txt")

#     def make_alternates_zip(self, alternates: dict[int, dict[str, list[str]]]) -> BufferedReader:
#         """Create a geonames alternates zip file"""
#         rows = []
#         for geoname_id, entry in alternates.items():
#             for iso_language, names in entry.items():
#                 for name in names:
#                     row = [""] * (MAX_ALTERNATES_COL + 1)
#                     row[ALTERNATES_COL_GEONAME_ID] = str(geoname_id)
#                     row[ALTERNATES_COL_ISO_LANGUAGE] = iso_language
#                     row[ALTERNATES_COL_NAME] = name
#                     rows.append(row)
#         return self.make_zip(rows, "US.txt")

    def make_alternates_zip(self, geonames: list[Geoname]) -> BufferedReader:
        """Create a geonames alternates zip file"""
        rows = []
        for geoname in geonames:
            for iso_language, names in geoname.alternates_by_iso_language.items():
                for name in names:
                    row = [""] * (MAX_ALTERNATES_COL + 1)
                    row[ALTERNATES_COL_GEONAME_ID] = str(geoname.id)
                    row[ALTERNATES_COL_ISO_LANGUAGE] = iso_language
                    row[ALTERNATES_COL_NAME] = name
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
# def downloader_test() -> DownloaderFixture:
def downloader_fixture(requests_mock) -> DownloaderFixture:
    """Return downloader fixture"""
    fixture = DownloaderFixture(requests_mock)
    yield fixture
    fixture.clean_up()


def with_alternates(geoname: Geoname, alts: dict[str, list[str]]) -> Geoname:
    g = deepcopy(geoname)
    g.alternates_by_iso_language = alts
    return g
