# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

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
    DownloadMetrics,
    DownloadState,
    Geoname,
    GeonamesDownloader,
)

from tests.unit.jobs.geonames_uploader.geonames_utils import (
    DownloaderFixture,
    downloader_fixture,
    with_alternates,
    SERVER_DATA,
    GEONAMES,
    GEONAME_WATERLOO_AL,
    GEONAME_AL,
    GEONAME_WATERLOO_IA,
    GEONAME_IA,
    GEONAME_NYC,
    GEONAME_NY_STATE,
)


class DownloaderTest(DownloaderFixture):
    """Downloader test fixture"""

    def __init__(self, requests_mock) -> None:
        """Initialize test"""
        super().__init__(requests_mock)

    def run(
        self,
        population_threshold: int,
        city_alternates_iso_languages: list[str],
        admin_alternates_iso_languages: list[str],
        expected_geonames: list[Geoname],
        expected_metrics: DownloadMetrics,
    ) -> None:
        """Run test"""
        downloader = GeonamesDownloader(
            base_url=SERVER_DATA["base_url"],
            geonames_path=SERVER_DATA["geonames_path"],
            alternates_path=SERVER_DATA["alternates_path"],
            country_code="US",
            city_alternates_iso_languages=city_alternates_iso_languages,
            admin_alternates_iso_languages=admin_alternates_iso_languages,
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
        expected_geonames_by_id = {g.id: g for g in expected_geonames}
        assert len(actual_state.geonames_by_id) == len(expected_geonames_by_id)
        for k, v in expected_geonames_by_id.items():
            assert k in actual_state.geonames_by_id
            assert actual_state.geonames_by_id[k] == v

        assert actual_state.metrics == expected_metrics


@pytest.fixture()
def downloader_test(requests_mock) -> DownloaderTest:
    """Return downloader test fixture"""
    return DownloaderTest(requests_mock)

def test_all_populations_and_iso_languages(
    downloader_test: DownloaderTest,
):
    """Request geonames with populations > 0 and alternates of all ISO languages
    in the datset

    """
    downloader_test.run(
        population_threshold=1,
        city_alternates_iso_languages=["en", "es", "abbr", "iata"],
        admin_alternates_iso_languages=["en", "es", "abbr"],
        expected_geonames=[
            with_alternates(GEONAME_WATERLOO_AL, {
                "en": ["Waterloo"],
            }),
            with_alternates(GEONAME_AL, {
                "abbr": ["AL"],
                "en": ["State of Alabama"],
            }),
            with_alternates(GEONAME_WATERLOO_IA, {
                "en": ["Waterloo"],
                "es": ["Waterloo"],
            }),
            with_alternates(GEONAME_IA, {
                "abbr": ["IA"],
                "en": ["State of Iowa"],
            }),
            with_alternates(GEONAME_NYC, {
                "abbr": ["NY", "NYC"],
                "en": ["New York", "Da Big Apple Baby"],
                "es": ["Nueva York"],
                "iata": ["LGA"],
            }),
            with_alternates(GEONAME_NY_STATE, {
                "abbr": ["NY"],
                "en": ["New York", "State of New York"],
                "es": ["Nueva York"],
            }),
        ],
        expected_metrics=DownloadMetrics(
            # No excluded cities or regions
            excluded_geonames_count=0,
            included_alternates_count=17,
        ),
    )


def test_one_million_population_and_all_iso_languages(
    downloader_test: DownloaderTest,
):
    """Request geonames with populations > one million and alternates of all ISO
    languages in the datset

    """
    downloader_test.run(
        population_threshold=1_000_000,
        city_alternates_iso_languages=["en", "es", "abbr", "iata"],
        admin_alternates_iso_languages=["en", "es", "abbr"],
        expected_geonames=[
            with_alternates(GEONAME_AL, {
                "abbr": ["AL"],
                "en": ["State of Alabama"],
            }),
            with_alternates(GEONAME_IA, {
                "abbr": ["IA"],
                "en": ["State of Iowa"],
            }),
            with_alternates(GEONAME_NYC, {
                "abbr": ["NY", "NYC"],
                "en": ["New York", "Da Big Apple Baby"],
                "es": ["Nueva York"],
                "iata": ["LGA"],
            }),
            with_alternates(GEONAME_NY_STATE, {
                "abbr": ["NY"],
                "en": ["New York", "State of New York"],
                "es": ["Nueva York"],
            }),
        ],
        expected_metrics=DownloadMetrics(
            # No Waterloo AL, Waterloo IA
            excluded_geonames_count=2,
            included_alternates_count=14,
        ),
    )


def test_one_million_population_and_en_only(
    downloader_test: DownloaderTest,
):
    """Request geonames with populations > one million, "en" and "abbr" alternates only"""
    downloader_test.run(
        population_threshold=1_000_000,
        city_alternates_iso_languages=["en"],
        admin_alternates_iso_languages=["abbr"],
        expected_geonames=[
            with_alternates(GEONAME_AL, {
                "abbr": ["AL"],
            }),
            with_alternates(GEONAME_IA, {
                "abbr": ["IA"],
            }),
            with_alternates(GEONAME_NYC, {
                "en": ["New York", "Da Big Apple Baby"],
            }),
            with_alternates(GEONAME_NY_STATE, {
                "abbr": ["NY"],
            }),
        ],
        expected_metrics=DownloadMetrics(
            excluded_geonames_count=2,
            included_alternates_count=5,
        ),
    )
