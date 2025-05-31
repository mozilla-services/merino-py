# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for downloader.py module."""

import pytest
from typing import Callable


from merino.jobs.geonames_uploader.downloader import (
    GeonamesDownload,
    download_geonames,
    GeonameAlternate,
    AlternatesDownload,
    download_alternates,
)

from tests.unit.jobs.geonames_uploader.geonames_utils import (
    DownloaderFixture,
    SERVER_DATA,
    GEONAMES,
    GEONAME_AL,
    GEONAME_WATERLOO_IA,
    GEONAME_IA,
    GEONAME_NYC,
    GEONAME_NY_STATE,
    ALTERNATES,
)


class GeonamesDownloaderTest(DownloaderFixture):
    """Geonames downloader test fixture"""

    def __init__(self, requests_mock) -> None:
        """Initialize test"""
        super().__init__(requests_mock)

    def run(
        self,
        population_threshold: int,
        expected_download: GeonamesDownload,
    ) -> None:
        """Run test"""
        download = download_geonames(
            country="US",
            population_threshold=population_threshold,
            url_format=SERVER_DATA["geonames_url_format"],
        )
        assert download == expected_download
        self.clean_up()


@pytest.fixture()
def geonames_downloader_test(requests_mock) -> GeonamesDownloaderTest:
    """Return geonames downloader test fixture"""
    return GeonamesDownloaderTest(requests_mock)


class AlternatesDownloaderTest(DownloaderFixture):
    """Alternates downloader test fixture"""

    def __init__(self, requests_mock) -> None:
        """Initialize test"""
        super().__init__(requests_mock)

    def run(
        self,
        languages: set[str],
        geoname_ids: set[int],
        expected_download: AlternatesDownload,
    ) -> None:
        """Run test"""
        download = download_alternates(
            country="US",
            languages=languages,
            geoname_ids=geoname_ids,
            url_format=SERVER_DATA["alternates_url_format"],
        )
        assert download == expected_download
        self.clean_up()


@pytest.fixture()
def alternates_downloader_test(requests_mock) -> AlternatesDownloaderTest:
    """Return alternates downloader test fixture"""
    return AlternatesDownloaderTest(requests_mock)


def filter_alternates(
    predicate: Callable[[int, str, GeonameAlternate], bool],
) -> dict[str, dict[int, list[GeonameAlternate]]]:
    """Filter `ALTERNATES` on a given predicate."""
    alts_by_geoname_id_by_lang: dict[str, dict[int, list[GeonameAlternate]]] = {}
    for lang, geoname_and_alts_tuples in ALTERNATES.items():
        for geoname, alts in geoname_and_alts_tuples:
            # The `AlternatesDownloaderTest` fixture only provides US geonames
            # and alternates, so ignore ones in other countries (Goessnitz).
            if geoname.country_code == "US":
                for alt in alts:
                    if predicate(geoname.id, lang, alt):
                        alts_by_geoname_id = alts_by_geoname_id_by_lang.setdefault(lang, {})
                        selected_alts = alts_by_geoname_id.setdefault(geoname.id, [])
                        selected_alts.append(alt)
    return alts_by_geoname_id_by_lang


def test_filter_alternates_on_geoname_id():
    """Test the `filter_alternates` test helper function."""
    actual = filter_alternates(lambda geoname_id, lang, alt: geoname_id == GEONAME_NYC.id)
    assert actual == {
        "abbr": {
            GEONAME_NYC.id: [
                GeonameAlternate("NY"),
                GeonameAlternate("NYC"),
            ],
        },
        "en": {
            GEONAME_NYC.id: [
                GeonameAlternate("New York", is_short=True, is_preferred=True),
                GeonameAlternate("New York City"),
            ],
        },
        "es": {
            GEONAME_NYC.id: [
                GeonameAlternate("Nueva York"),
            ],
        },
        "iata": {
            GEONAME_NYC.id: [
                GeonameAlternate("LGA"),
            ],
        },
    }


def test_filter_alternates_on_lang():
    """Test the `filter_alternates` test helper function."""
    actual = filter_alternates(lambda geoname_id, lang, alt: lang == "es")
    assert actual == {
        "es": {
            GEONAME_WATERLOO_IA.id: [
                GeonameAlternate("Waterloo"),
            ],
            GEONAME_NYC.id: [
                GeonameAlternate("Nueva York"),
            ],
            GEONAME_NY_STATE.id: [
                GeonameAlternate("Nueva York"),
            ],
        },
    }


def test_geonames_all(
    geonames_downloader_test: GeonamesDownloaderTest,
):
    """Request all geonames"""
    geonames_downloader_test.run(
        population_threshold=1,
        expected_download=GeonamesDownload(
            population_threshold=1,
            geonames=GEONAMES,
        ),
    )


def test_geonames_large_population_threshold(
    geonames_downloader_test: GeonamesDownloaderTest,
):
    """Request geonames with a large population threshold"""
    geonames_downloader_test.run(
        population_threshold=1_000_000,
        expected_download=GeonamesDownload(
            population_threshold=1_000_000,
            geonames=[GEONAME_AL, GEONAME_IA, GEONAME_NYC, GEONAME_NY_STATE],
        ),
    )


def test_alternates_all(
    alternates_downloader_test: AlternatesDownloaderTest,
):
    """Request all alternates"""
    languages = set(["abbr", "en", "es", "iata"])
    geoname_ids = set(g.id for g in GEONAMES)
    alternates_downloader_test.run(
        languages=languages,
        geoname_ids=geoname_ids,
        expected_download=AlternatesDownload(
            languages=languages,
            geoname_ids=geoname_ids,
            alternates_by_geoname_id_by_language=filter_alternates(
                lambda geoname_id, lang, alt: True
            ),
        ),
    )


def test_alternates_en(
    alternates_downloader_test: AlternatesDownloaderTest,
):
    """Request en alternates"""
    languages = set(["en"])
    geoname_ids = set(g.id for g in GEONAMES)
    alternates_downloader_test.run(
        languages=languages,
        geoname_ids=geoname_ids,
        expected_download=AlternatesDownload(
            languages=languages,
            geoname_ids=geoname_ids,
            alternates_by_geoname_id_by_language=filter_alternates(
                lambda geoname_id, lang, alt: lang == "en"
            ),
        ),
    )


def test_alternates_specific_geoname(
    alternates_downloader_test: AlternatesDownloaderTest,
):
    """Request alternates for a specific geoname"""
    languages = set(["abbr", "en"])
    geoname_ids = set([GEONAME_NYC.id])
    alternates_downloader_test.run(
        languages=languages,
        geoname_ids=geoname_ids,
        expected_download=AlternatesDownload(
            languages=languages,
            geoname_ids=geoname_ids,
            alternates_by_geoname_id_by_language=filter_alternates(
                lambda geoname_id, lang, alt: geoname_id == GEONAME_NYC.id
                and lang in ["en", "abbr"]
            ),
        ),
    )
