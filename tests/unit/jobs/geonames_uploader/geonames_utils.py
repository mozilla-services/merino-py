# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Helpers for the geonames-downloader tests."""

import csv
import pytest
from typing import Generator, Tuple

from io import BufferedReader

from tempfile import NamedTemporaryFile
from zipfile import ZipFile

from merino.jobs.geonames_uploader.downloader import (
    GEONAME_COL_ID,
    GEONAME_COL_NAME,
    GEONAME_COL_ASCII_NAME,
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
    ALTERNATES_COL_IS_PREFERRED,
    ALTERNATES_COL_IS_SHORT,
    MAX_ALTERNATES_COL,
    Geoname,
    GeonameAlternate,
)

from merino.jobs.geonames_uploader.alternates import _rs_alternates_list, RsAlternate
from merino.jobs.geonames_uploader.geonames import _rs_geoname


SERVER_DATA = {
    "geonames_url_format": "http://geonames/export/dump/{country}.zip",
    "alternates_url_format": "http://geonames/export/dump/alternatenames/{country}.zip",
}

GEONAME_WATERLOO_AL = Geoname(
    id=4096497,
    name="Waterloo",
    ascii_name="Waterloo",
    feature_class="P",
    feature_code="PPL",
    country_code="US",
    admin1_code="AL",
    admin2_code="077",
    admin3_code=None,
    admin4_code=None,
    population=200,
    latitude="34.91814",
    longitude="-88.0642",
)

GEONAME_AL = Geoname(
    id=4829764,
    name="Alabama",
    ascii_name="Alabama",
    feature_class="A",
    feature_code="ADM1",
    country_code="US",
    admin1_code="AL",
    admin2_code=None,
    admin3_code=None,
    admin4_code=None,
    population=4530315,
    latitude="32.75041",
    longitude="-86.75026",
)

GEONAME_WATERLOO_IA = Geoname(
    id=4880889,
    name="Waterloo",
    ascii_name="Waterloo",
    feature_class="P",
    feature_code="PPLA2",
    country_code="US",
    admin1_code="IA",
    admin2_code="013",
    admin3_code="94597",
    admin4_code="ABC",
    population=68460,
    latitude="42.49276",
    longitude="-92.34296",
)

GEONAME_IA = Geoname(
    id=4862182,
    name="Iowa",
    ascii_name="Iowa",
    feature_class="A",
    feature_code="ADM1",
    country_code="US",
    admin1_code="IA",
    admin2_code=None,
    admin3_code=None,
    admin4_code=None,
    population=2955010,
    latitude="42.00027",
    longitude="-93.50049",
)

GEONAME_NYC = Geoname(
    id=5128581,
    name="New York City",
    ascii_name="New York City",
    feature_class="P",
    feature_code="PPL",
    country_code="US",
    admin1_code="NY",
    admin2_code=None,
    admin3_code=None,
    admin4_code=None,
    population=8804190,
    latitude="40.71427",
    longitude="-74.00597",
)

GEONAME_NY_STATE = Geoname(
    id=5128638,
    name="New York",
    ascii_name="New York",
    feature_class="A",
    feature_code="ADM1",
    country_code="US",
    admin1_code="NY",
    admin2_code=None,
    admin3_code=None,
    admin4_code=None,
    population=19274244,
    latitude="43.00035",
    longitude="-75.4999",
)

GEONAME_SACRAMENTO = Geoname(
    id=5389489,
    name="Sacramento",
    ascii_name="Sacramento",
    feature_class="P",
    feature_code="PPLA",
    country_code="US",
    admin1_code="CA",
    admin2_code="067",
    admin3_code=None,
    admin4_code=None,
    population=490712,
    latitude="38.58157",
    longitude="-121.4944",
)

GEONAME_WATERLOO_ON = Geoname(
    id=6176823,
    name="Waterloo",
    ascii_name="Waterloo",
    feature_class="P",
    feature_code="PPL",
    country_code="CA",
    admin1_code="08",
    admin2_code="3530",
    admin3_code=None,
    admin4_code=None,
    population=104986,
    latitude="43.4668",
    longitude="-80.51639",
)

GEONAME_HALIFAX = Geoname(
    id=6324729,
    name="Halifax",
    ascii_name="Halifax",
    feature_class="P",
    feature_code="PPLA",
    country_code="CA",
    admin1_code="07",
    admin2_code="1209",
    admin3_code=None,
    admin4_code=None,
    population=439819,
    latitude="44.64269",
    longitude="-63.57688",
)

GEONAME_VANCOUVER = Geoname(
    id=6173331,
    name="Vancouver",
    ascii_name="Vancouver",
    feature_class="P",
    feature_code="PPL",
    country_code="CA",
    admin1_code="02",
    admin2_code="5915",
    admin3_code=None,
    admin4_code=None,
    population=600000,
    latitude="49.24966",
    longitude="-123.11934",
)

GEONAME_GOESSNITZ = Geoname(
    id=2918770,
    name="Gößnitz",
    # ascii_name != name
    ascii_name="Goessnitz",
    feature_class="P",
    feature_code="PPL",
    country_code="DE",
    admin1_code="15",
    admin2_code="00",
    admin3_code="16077",
    admin4_code="16077012",
    population=4104,
    latitude="50.88902",
    longitude="12.43292",
)

GEONAME_KIEL = Geoname(
    id=2918770,
    name="Kiel",
    ascii_name="Kiel",
    feature_class="P",
    feature_code="PPLA",
    country_code="DE",
    admin1_code="10",
    admin2_code="00",
    admin3_code="01002",
    admin4_code="01002000",
    population=246601,
    latitude="54.32133",
    longitude="10.13489",
)

GEONAME_BERLIN = Geoname(
    id=2950159,
    name="Berlin",
    ascii_name="Berlin",
    feature_class="P",
    feature_code="PPLC",
    country_code="DE",
    admin1_code="16",
    admin2_code="00",
    admin3_code="11000",
    admin4_code="11000000",
    population=3426354,
    latitude="52.52437",
    longitude="13.41053",
)

GEONAME_GUADALUPE = Geoname(
    id=4005509,
    name="Guadalupe",
    ascii_name="Guadalupe",
    feature_class="P",
    feature_code="PPLA2",
    country_code="MX",
    admin1_code="32",
    admin2_code="17",
    admin3_code=None,
    admin4_code=None,
    population=215000,
    latitude="22.74753",
    longitude="-102.51874",
)

GEONAME_MEXICO_CITY = Geoname(
    id=3530597,
    name="Mexico City",
    ascii_name="Mexico City",
    feature_class="P",
    feature_code="PPLC",
    country_code="MX",
    admin1_code="09",
    admin2_code=None,
    admin3_code=None,
    admin4_code=None,
    population=12294193,
    latitude="19.42847",
    longitude="-99.12766",
)

GEONAMES_BY_COUNTRY = {
    "DE": [
        GEONAME_GOESSNITZ,
        GEONAME_KIEL,
        GEONAME_BERLIN,
    ],
    "CA": [
        GEONAME_WATERLOO_ON,
        GEONAME_HALIFAX,
        GEONAME_VANCOUVER,
    ],
    "MX": [
        GEONAME_GUADALUPE,
        GEONAME_MEXICO_CITY,
    ],
    "US": [
        GEONAME_WATERLOO_AL,
        GEONAME_AL,
        GEONAME_WATERLOO_IA,
        GEONAME_IA,
        GEONAME_NYC,
        GEONAME_NY_STATE,
        GEONAME_SACRAMENTO,
    ],
}

ALTERNATES_BY_COUNTRY = {
    "DE": {
        "en": [
            (
                GEONAME_GOESSNITZ,
                [
                    GeonameAlternate("Gößnitz"),
                    GeonameAlternate("Goessnitz"),
                    GeonameAlternate("Gössnitz"),
                ],
            ),
        ],
    },
    "US": {
        "abbr": [
            (GEONAME_AL, [GeonameAlternate("AL")]),
            (GEONAME_IA, [GeonameAlternate("IA")]),
            (GEONAME_NYC, [GeonameAlternate("NY"), GeonameAlternate("NYC")]),
            (GEONAME_NY_STATE, [GeonameAlternate("NY")]),
        ],
        "en": [
            (GEONAME_WATERLOO_AL, [GeonameAlternate("Waterloo")]),
            (GEONAME_AL, [GeonameAlternate("State of Alabama")]),
            (GEONAME_WATERLOO_IA, [GeonameAlternate("Waterloo")]),
            (GEONAME_IA, [GeonameAlternate("State of Iowa")]),
            (
                GEONAME_NYC,
                [
                    GeonameAlternate("New York", is_preferred=True, is_short=True),
                    GeonameAlternate("New York City"),
                ],
            ),
            (GEONAME_NY_STATE, [GeonameAlternate("State of New York")]),
            (GEONAME_SACRAMENTO, [GeonameAlternate("Sac")]),
        ],
        "es": [
            (GEONAME_WATERLOO_IA, [GeonameAlternate("Waterloo")]),
            (GEONAME_NYC, [GeonameAlternate("Nueva York")]),
            (GEONAME_NY_STATE, [GeonameAlternate("Nueva York")]),
        ],
        "fr": [
            (GEONAME_NY_STATE, [GeonameAlternate("État de New York")]),
        ],
        "iata": [
            (GEONAME_NYC, [GeonameAlternate("LGA")]),
        ],
        # an unused/unrecognized language
        "xx": [
            (GEONAME_NYC, [GeonameAlternate("New York Xx")]),
        ],
    },
}


class DownloaderFixture:
    """Downloader test fixture. Creates geonames and alternates zip files and
    mocks requests for them.
    """

    # country => (geonames_zip, alternates_zip)
    zips_by_country: dict[str, Tuple[BufferedReader, BufferedReader]]

    def __init__(
        self,
        requests_mock,
        countries: list[str] = [c for c in GEONAMES_BY_COUNTRY.keys()],
    ):
        """Initialize fixture"""
        self.zips_by_country = {}
        for country in countries:
            geonames = self.make_geonames_zip(GEONAMES_BY_COUNTRY[country], country)
            alternates = self.make_alternates_zip(ALTERNATES_BY_COUNTRY.get(country, {}), country)

            self.zips_by_country[country] = (geonames, alternates)

            geonames_url = SERVER_DATA["geonames_url_format"].format(country=country)
            alternates_url = SERVER_DATA["alternates_url_format"].format(country=country)
            requests_mock.get(geonames_url, body=geonames)
            requests_mock.get(alternates_url, body=alternates)

    def make_geonames_zip(self, geonames: list[Geoname], country: str) -> BufferedReader:
        """Create a geonames zip file"""
        rows = []
        for g in geonames:
            row = [""] * (MAX_GEONAME_COL + 1)
            row[GEONAME_COL_ID] = str(g.id)
            row[GEONAME_COL_NAME] = g.name
            row[GEONAME_COL_ASCII_NAME] = g.ascii_name
            row[GEONAME_COL_LATITUDE] = g.latitude or ""
            row[GEONAME_COL_LONGITUDE] = g.longitude or ""
            row[GEONAME_COL_FEATURE_CLASS] = g.feature_class
            row[GEONAME_COL_FEATURE_CODE] = g.feature_code
            row[GEONAME_COL_COUNTRY_CODE] = g.country_code
            row[GEONAME_COL_ADMIN1_CODE] = g.admin1_code or ""
            row[GEONAME_COL_ADMIN2_CODE] = g.admin2_code or ""
            row[GEONAME_COL_ADMIN3_CODE] = g.admin3_code or ""
            row[GEONAME_COL_ADMIN4_CODE] = g.admin4_code or ""
            row[GEONAME_COL_POPULATION] = str(g.population)
            rows.append(row)
        return self.make_zip(rows, f"{country}.txt")

    def make_alternates_zip(
        self,
        alternates: dict[str, list[Tuple[Geoname, list[GeonameAlternate]]]],
        country: str,
    ) -> BufferedReader:
        """Create a geonames alternates zip file"""
        rows = []
        for lang, geoname_alts_tuples in alternates.items():
            for geoname, alts in geoname_alts_tuples:
                for alt in alts:
                    row = [""] * (MAX_ALTERNATES_COL + 1)
                    row[ALTERNATES_COL_GEONAME_ID] = str(geoname.id)
                    row[ALTERNATES_COL_ISO_LANGUAGE] = lang
                    row[ALTERNATES_COL_NAME] = alt.name
                    row[ALTERNATES_COL_IS_PREFERRED] = "1" if alt.is_preferred else ""
                    row[ALTERNATES_COL_IS_SHORT] = "1" if alt.is_short else ""
                    rows.append(row)
        return self.make_zip(rows, f"{country}.txt")

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
        for geonames_zip, alternates_zip in self.zips_by_country.values():
            geonames_zip.close()
            alternates_zip.close()


@pytest.fixture()
def downloader_fixture(requests_mock) -> Generator:
    """Return downloader fixture"""
    fixture = DownloaderFixture(requests_mock)
    yield fixture
    fixture.clean_up()


def filter_geonames(
    country: str,
    lower_threshold: int,
    upper_threshold: int | None = None,
) -> list[Geoname]:
    """Return geonames for the given country and population partition."""
    return [
        g
        for g in GEONAMES_BY_COUNTRY[country]
        if lower_threshold <= (g.population or 0)
        and (upper_threshold is None or (g.population or 0) < upper_threshold)
    ]


def filter_alternates(
    country: str,
    language: str,
    geonames: list[Geoname],
) -> list[list[int | list[RsAlternate]]]:
    """Filter all alternates on a language and geonames and return a list of
    tuples appropriate for comparing to data in remote settings attachments. The
    tuples are actually lists since tuples are lists in JSON.

    """
    return [
        # Convert the (geoname_id, rd_alts) tuple to a list.
        list(tup)
        for tup in _rs_alternates_list(
            [
                (_rs_geoname(geoname), alts)
                for geoname, alts in ALTERNATES_BY_COUNTRY[country][language]
                if geoname in geonames
            ]
        )
    ]
