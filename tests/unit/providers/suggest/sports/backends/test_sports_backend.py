"""Test Gauntlet for SportsData.io"""

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import freezegun
import httpx
import pytest
from pytest_mock import MockerFixture

from merino.configs import settings
from merino.providers.suggest.sports.backends import SPORTSDATA_STALE_FALLBACK_METRIC, get_data
from merino.providers.suggest.sports.backends.sportsdata.backend import (
    SportsDataBackend,
)
from merino.providers.suggest.sports.backends.sportsdata.common import (
    GameStatus,
    SportCategory,
)
from merino.providers.suggest.sports.backends.sportsdata.common.data import (
    Team,
    SportTerms,
    SPORTSDATA_API_KEY_HEADER,
)
from merino.providers.suggest.sports.backends.sportsdata.common.error import SportsDataError
from merino.providers.suggest.sports.backends.sportsdata.common.elastic import (
    ElasticCredentials,
    SportsDataStore,
)
from merino.providers.suggest.sports.backends.sportsdata.protocol import (
    SportEventDetail,
    SportSummary,
    build_query,
)
from merino.utils.logos import Logo, LogoCategory, LogoManifest


VALID_TEST_RESPONSE: dict = {}


@pytest.mark.asyncio
async def test_get_data():
    """Simple test for the `get_data` caching fetcher."""
    ttl = timedelta(seconds=5)
    with patch.object(
        httpx.AsyncClient,
        "get",
        return_value=httpx.Response(status_code=200, json=dict(foo="bar")),
    ) as mock_client:
        mock_res = {"foo": "bar"}
        with patch.object(json, "dump") as mock_json:
            await get_data(
                client=mock_client,
                url="http://example.org",
                ttl=ttl,
                cache_dir="/tmp",  # nosec
                args={"key": "abc123"},
            )
            # was the URL called?
            mock_client.get.assert_called_with("http://example.org", params={"key": "abc123"})
            # see if it tried to write the file to the cache dir...
            assert (
                mock_json.call_args_list[0].args[1].buffer.name
                == "/tmp/ff7c1f10ab54968058fdcfaadf1b2457cd5d1a3f.json"  # nosec
            )
            with patch.object(json, "load") as mock_load:
                mock_load.return_value = mock_res
                ttl = timedelta(days=5)
                res = await get_data(
                    client=mock_client,
                    url="http://example.org",
                    ttl=ttl,
                    cache_dir="/tmp",  # nosec
                )
                assert mock_load.call_count == 1
                assert res == mock_res


@pytest.mark.asyncio
async def test_get_data_with_no_cache_dir():
    """Test for `get_data` with no cache dir."""
    ttl = timedelta(seconds=5)
    with patch.object(
        httpx.AsyncClient,
        "get",
        return_value=httpx.Response(status_code=200, json=dict(foo="bar")),
    ) as mock_client:
        with patch.object(json, "dump") as mock_json:
            await get_data(
                client=mock_client, url="http://example.org", ttl=ttl, args={"key": "abc123"}
            )
            mock_client.get.assert_called_with("http://example.org", params={"key": "abc123"})
            mock_json.assert_not_called()


@pytest.mark.asyncio
async def test_get_data_sends_headers():
    """Test for `get_data` with request headers."""
    api_key = "sports-secret"
    mock_response = httpx.Response(
        status_code=403,
        request=httpx.Request("GET", "http://example.org"),
    )
    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    with pytest.raises(SportsDataError) as exc_info:
        await get_data(
            client=mock_client,
            url="http://example.org",
            headers={SPORTSDATA_API_KEY_HEADER: api_key},
        )

    mock_client.get.assert_awaited_once_with(
        "http://example.org",
        params=None,
        headers={SPORTSDATA_API_KEY_HEADER: api_key},
    )
    assert api_key not in str(exc_info.value)
    assert "status 403" in str(exc_info.value)
    assert exc_info.value.__cause__ is None


@pytest.mark.asyncio
async def test_get_data_retries_transient_provider_fetch_failures(mocker: MockerFixture):
    """Test that `get_data` retries transient provider fetch errors."""
    mock_response_error = httpx.Response(
        status_code=503,
        request=httpx.Request("GET", "http://example.org"),
    )
    mock_response_success = httpx.Response(
        status_code=200,
        json={"ok": True},
        request=httpx.Request("GET", "http://example.org"),
    )
    mock_client = MagicMock()
    mock_client.get = AsyncMock(side_effect=[mock_response_error, mock_response_success])
    sleep = mocker.patch(
        "merino.providers.suggest.sports.backends._sportsdata_retry_sleep",
        new=mocker.AsyncMock(),
    )

    data = await get_data(
        client=mock_client,
        url="http://example.org",
    )

    assert data == {"ok": True}
    assert mock_client.get.await_count == 2
    assert sleep.await_count == 1


@pytest.mark.asyncio
@freezegun.freeze_time("2099-01-01T00:00:00", tz_offset=0)
async def test_get_data_returns_stale_cache_when_provider_fetch_fails(
    mocker: MockerFixture, tmp_path: Path
):
    """Test that `get_data` falls back to stale cache after provider fetch errors."""
    ttl = timedelta(seconds=5)
    url = "http://example.org"
    cached_data = {"stale": True}
    hasher = hashlib.new("sha1", usedforsecurity=False)
    hasher.update(url.encode())
    cache_file = tmp_path / f"{hasher.hexdigest()}.json"
    cache_file.write_text(json.dumps(cached_data))
    mock_response = httpx.Response(
        status_code=503,
        request=httpx.Request("GET", url),
    )
    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    metrics_client = mocker.patch(
        "merino.providers.suggest.sports.backends.get_metrics_client"
    ).return_value
    sleep = mocker.patch(
        "merino.providers.suggest.sports.backends._sportsdata_retry_sleep",
        new=mocker.AsyncMock(),
    )

    with patch.object(json, "dump") as mock_dump:
        data = await get_data(
            client=mock_client,
            url=url,
            ttl=ttl,
            cache_dir=str(tmp_path),
        )

    assert mock_client.get.await_count == settings.providers.sports.sportsdata.retry_max_tries
    mock_client.get.assert_awaited_with(url, params=None)
    assert sleep.await_count == settings.providers.sports.sportsdata.retry_max_tries - 1
    metrics_client.increment.assert_called_once_with(
        SPORTSDATA_STALE_FALLBACK_METRIC, tags={"status": "503"}
    )
    mock_dump.assert_not_called()
    assert data == cached_data


@pytest.mark.asyncio
async def test_get_data_handles_permission_error():
    """Test for `get_data` handles permission error."""
    ttl = timedelta(seconds=5)
    with patch.object(
        httpx.AsyncClient,
        "get",
        return_value=httpx.Response(status_code=200, json=dict(foo="bar")),
    ) as mock_client:
        with (
            patch.object(os.path, "exists", return_value=True),
            patch.object(os.path, "getctime", side_effect=PermissionError),
            patch.object(json, "dump"),
        ):
            await get_data(
                client=mock_client,
                url="http://example.org",
                ttl=ttl,
                cache_dir="/tmp",  # nosec
                args={"key": "12345"},
            )
            # Permission Error file not read, request need to be made
            mock_client.get.assert_called_with("http://example.org", params={"key": "12345"})


@pytest.mark.asyncio
@freezegun.freeze_time("2025-09-22T00:00:00", tz_offset=0)
async def test_get_data_cache_file_exists():
    """Test for `get_data` handles cache file exists."""
    ttl = timedelta(days=1)
    with patch.object(
        httpx.AsyncClient,
        "get",
        return_value=httpx.Response(status_code=200, json=dict(foo="bar")),
    ) as mock_client:
        with (
            patch.object(os.path, "exists", return_value=True),
            patch.object(os.path, "getctime", return_value=datetime.now().timestamp()),
            patch.object(json, "load", return_value={"bar": "foo"}),
        ):
            data = await get_data(
                client=mock_client,
                url="http://example.org",
                ttl=ttl,
                cache_dir="/tmp",  # nosec
            )
            mock_client.get.assert_not_called()
            assert data == {"bar": "foo"}


# sports/backends/sportsdata/common:
@pytest.mark.asyncio
async def test_gamestatus():
    """Test the GameStatus enum"""
    assert GameStatus.parse("final") == GameStatus.Final
    assert GameStatus.parse("in progress") == GameStatus.InProgress
    assert GameStatus.parse("break") == GameStatus.Break
    assert GameStatus.parse("final - over time") == GameStatus.F_OT
    assert GameStatus.parse("final - shoot out") == GameStatus.F_SO
    assert GameStatus.parse("not necessary") == GameStatus.NotNecessary
    assert GameStatus.parse("Banana") == GameStatus.Unknown

    assert GameStatus.Final.is_final()
    assert GameStatus.parse("scheduled").is_scheduled()
    assert GameStatus.parse("break").is_in_progress()
    assert GameStatus.parse("suspended").is_in_progress()
    assert GameStatus.parse("In Progress").status_type() == GameStatus.InProgress
    assert GameStatus.NotNecessary.as_str() == "Not Necessary"
    assert GameStatus.Final.status_type() == GameStatus.Final
    assert GameStatus.F_OT.status_type() == GameStatus.Final
    assert GameStatus.Scheduled.status_type() == GameStatus.Scheduled

    assert GameStatus.Final.as_ui_status() == "past"
    assert GameStatus.InProgress.as_ui_status() == "live"
    assert GameStatus.Break.as_ui_status() == "live"
    assert GameStatus.Scheduled.as_ui_status() == "scheduled"
    assert GameStatus.Unknown.as_ui_status() == "unknown"

    assert GameStatus.InProgress.as_str() == "In Progress"
    assert GameStatus.F_OT.as_str() == "Final - Over Time"
    assert GameStatus.F_SO.as_str() == "Final - Shoot Out"
    assert GameStatus.NotNecessary.as_str() == "Not Necessary"
    assert GameStatus.Unknown.as_str() == ""
    assert GameStatus.Canceled.as_str() == "Canceled"


@pytest.mark.asyncio
async def test_team():
    """Test the team parser"""
    team_data = {
        "TeamId": 694,
        "AreaId": 203,
        "VenueId": 437,
        "Key": "CHI",
        "Name": "Chicago Fire FC",
        "FullName": "Chicago Fire Football Club",
        "Active": True,
        "AreaName": "United States",
        "VenueName": "Soldier Field",
        "Gender": "Male",
        "Type": "Club",
        "Address": None,
        "City": "Chicago",
        "Zip": None,
        "Phone": None,
        "Fax": None,
        "Website": "http://www.chicago-fire.com",
        "Email": None,
        "Founded": 1997,
        "ClubColor1": "FF0000",
        "ClubColor2": "FFFFFF",
        "ClubColor3": None,
        "Nickname1": "The Fire",
        "Nickname2": "La Máquina Roja",
        "Nickname3": "Men in Red",
        "WikipediaLogoUrl": "https://upload.wikimedia.org/wikipedia/commons/0/03/Chicago_Fire_logo%2C_2021.svg",
        "WikipediaWordMarkUrl": None,
        "GlobalTeamId": 90000694,
    }
    ttl = timedelta(seconds=300)
    team = Team.from_data(
        team_data=team_data,
        term_filter=["La", "The", "fc"],
        team_ttl=ttl,
        # Semi-hack unless you want to instantiate a version of UCL
        normalized_terms={
            SportTerms.TEAM_ID: "TeamId",
            SportTerms.COLOR1: "ClubColor1",
            SportTerms.COLOR2: "ClubColor2",
            SportTerms.COLOR3: "ClubColor3",
            SportTerms.COLOR4: "ClubColor4",
        },
    )
    assert team.key == "CHI"
    assert team.locale == "Chicago United States"
    assert team.colors == ["FF0000", "FFFFFF"]
    assert "fire" in team.terms
    assert "chicago" in team.terms


@pytest.fixture(name="es_client")
def fixture_es_client(mocker: MockerFixture) -> MagicMock:
    """Test ElasticSearch client instance."""
    client = mocker.MagicMock()
    client.close = mocker.AsyncMock()

    indices = mocker.MagicMock()
    indices.create = mocker.AsyncMock()
    indices.delete = mocker.AsyncMock()
    indices.refresh = mocker.AsyncMock()
    client.indices = indices

    client.delete_by_query = mocker.AsyncMock()
    client.search = mocker.AsyncMock()
    return cast(MagicMock, client)


@pytest.fixture(name="sport_data_store")
def fixture_sport_data_store(es_client: MagicMock, statsd_mock: Any) -> SportsDataStore:
    """Test Sport Data Store instance"""
    creds = ElasticCredentials(
        dsn="http://es.test:9200",
        api_key="test-key",
    )
    s = SportsDataStore(
        credentials=creds,
        languages=["en"],
        platform="test",
        index_map={"event": "sports-en-events-test"},
        metrics_client=statsd_mock,
    )
    s.client = es_client
    return s


@pytest.mark.asyncio
async def test_sportsdata_backend(sport_data_store: SportsDataStore, mocker: MockerFixture):
    """Test the backend"""
    sport_data_store.search_events = AsyncMock(  # type: ignore
        side_effect=[
            {
                "all": {
                    "previous": {
                        "sport": "NHL",
                        "id": 30024036,
                        "date": "2025-10-16T16:00:00",
                        "home_team": {
                            "key": "PHI",
                            "name": "Philadelphia Flyers",
                            "colors": ["D24303", "000000", "FFFFFF"],
                        },
                        "away_team": {
                            "key": "WPG",
                            "name": "Winnipeg Jets",
                            "colors": ["041E42", "004A98", "A2AAAD", "A6192E"],
                        },
                        "home_score": 2,
                        "away_score": 5,
                        "status": "Final",
                        "expiry": "2025-10-19T17:50:59",
                        "es_score": 3.3510802,
                        "event_status": GameStatus.Final,
                    },
                    "next": {
                        "sport": "NFL",
                        "id": 19175,
                        "date": "2025-10-26T10:00:00",
                        "home_team": {
                            "key": "CIN",
                            "name": "Cincinnati Bengals",
                            "colors": ["000000", "FB4F14", "FFFFFF"],
                        },
                        "away_team": {
                            "key": "NYJ",
                            "name": "New York Jets",
                            "colors": ["115740", "FFFFFF", "000000"],
                        },
                        "home_score": None,
                        "away_score": None,
                        "status": "Scheduled",
                        "expiry": "2025-10-31T17:50:58",
                        "es_score": 3.0596066,
                        "event_status": GameStatus.Scheduled,
                    },
                }
            }
        ]
    )

    backend = SportsDataBackend(settings=settings.providers.sports, store=sport_data_store)
    res = await backend.query(
        query_string="Some Search String",
    )
    assert len(res) == 1
    summary = res[0]
    assert summary.sport == "all"
    assert len(summary.values) == 2


@pytest.mark.asyncio
async def test_sports_backend_startup(sport_data_store: SportsDataStore, mocker: MockerFixture):
    """Test that the backend calls the storage startup"""
    mock_store = AsyncMock()
    # Create and test the backend
    backend = SportsDataBackend(settings=settings.providers.sports, store=mock_store)
    await backend.startup()

    assert mock_store.startup.called


@pytest.mark.parametrize(
    "sport,expected_category",
    [
        ("NFL", SportCategory.Football),
        ("NHL", SportCategory.Hockey),
        ("NBA", SportCategory.Basketball),
        ("UCL", SportCategory.Soccer),
        ("MLB", SportCategory.Baseball),
        ("WCS", SportCategory.Soccer),
        ("WORLD CUP", SportCategory.Soccer),
        ("FIFA", SportCategory.Soccer),
        ("Warhammer40k", SportCategory.Misc),
    ],
    ids=["NFL", "NHL", "NBA", "UCL", "MLB", "WCS", "WORLD CUP", "FIFA", "miscellaneous"],
)
def test_sport_event_detail_category(sport: str, expected_category: SportCategory) -> None:
    """Test sport name mapping and fallback behavior"""
    base_event: dict = {
        "date": "2025-10-01T00:00:00+00:00",
        "event_status": GameStatus.Scheduled,
        "home_team": {"key": "HOM", "name": "Home Team", "colors": ["000000"]},
        "away_team": {"key": "AWY", "name": "Away Team", "colors": ["FFFFFF"]},
        "home_score": None,
        "away_score": None,
        "touched": "2025-10-01T00:00:00+00:00",
    }

    event = {**base_event, "sport": sport}
    result = SportEventDetail.from_event_dict(event)
    assert result.sport_category == expected_category


def test_sport_event_detail_remap() -> None:  # WCS, Widget
    """Test sport name mapping and fallback behavior"""
    event: dict = {
        "sport": "fifa",
        "date": "2025-10-01T00:00:00+00:00",
        "event_status": GameStatus.Scheduled,
        "home_team": {"key": "HOM", "name": "Home Team", "colors": ["000000"]},
        "away_team": {"key": "AWY", "name": "Away Team", "colors": ["FFFFFF"]},
        "home_score": None,
        "away_score": None,
        "touched": "2025-10-01T00:00:00+00:00",
    }

    result = SportEventDetail.from_event_dict(event)
    assert result.sport == "World Cup"
    assert result.query == "Home Team vs Away Team World Cup 2026"
    assert result.sport_category == SportCategory.Soccer


@pytest.mark.parametrize(
    "home_team_name,away_team_name,sport,stage,expected",
    [
        ("Home Team", "Away Team", "NFL", None, "NFL Home Team vs Away Team 01 October 2025"),
        ("Switzerland", "Germany", "FIFA", "Group", "Switzerland vs Germany World Cup 2026"),
        ("Japan", None, "FIFA", "Round of 16", "Round of 16 World Cup 2026"),
        (None, None, "FIFA", "Round of 32", "Round of 32 World Cup 2026"),
        ("South Korea", "TBD", "FIFA", "Semi-Finals", "Semi-Finals World Cup 2026"),
        ("TBD", "TBD", "FIFA", "3rd Place", "3rd Place World Cup 2026"),
    ],
    ids=["NFL", "WCS", "WCS: None (one)", "WCS: None (both)", "WCS: TBD (one)", "WCS: TBD (both)"],
)
def test_build_query(home_team_name, away_team_name, sport, stage, expected) -> None:
    """build_query produces a 'sport away vs home date' string."""
    event: dict = {
        "sport": sport,
        "date": "2025-10-01T16:00:00+00:00",
        "home_team": {
            "name": home_team_name,
            "key": home_team_name,
            "id": 0 if home_team_name == "TBD" else 123,
        }
        if home_team_name is not None
        else None,
        "away_team": {
            "name": away_team_name,
            "key": away_team_name,
            "id": 0 if away_team_name == "TBD" else 345,
        }
        if away_team_name is not None
        else None,
        "stage": stage,
    }
    assert build_query(event) == expected


def test_build_query_uses_league_local_date() -> None:
    """build_query uses the SportsData league-local date for final US sports."""
    event: dict = {
        "sport": "MLB",
        "event_status": GameStatus.Final,
        "date": "2026-05-13T02:10:00+00:00",
        "original_date": "2026-05-12T00:00:00",
        "home_team": {"name": "Los Angeles Dodgers"},
        "away_team": {"name": "San Francisco Giants"},
    }

    assert build_query(event) == "MLB Los Angeles Dodgers vs San Francisco Giants 12 May 2026"


def test_build_query_uses_source_day_for_scheduled_us_sports() -> None:
    """build_query uses the SportsData source day for scheduled US sports."""
    event: dict = {
        "sport": "NFL",
        "event_status": GameStatus.Scheduled,
        "date": "2025-10-27T00:10:00+00:00",
        "original_date": "2025-10-26T00:00:00",
        "home_team": {"name": "Fake Home"},
        "away_team": {"name": "Fake Away"},
    }

    assert build_query(event) == "NFL Fake Home vs Fake Away 26 October 2025"


def test_sport_summary_current_suppresses_previous_and_keeps_next() -> None:
    """SportSummary returns current and next events when both are available."""

    def event(status: GameStatus, date: str) -> dict[str, Any]:
        return {
            "sport": "TEST",
            "event_status": status,
            "date": date,
            "home_team": {"key": "HOM", "name": "Home Team", "colors": ["000000"]},
            "away_team": {"key": "AWY", "name": "Away Team", "colors": ["FFFFFF"]},
            "home_score": None,
            "away_score": None,
            "touched": "2026-05-13T00:00:00+00:00",
        }

    summary = SportSummary.from_events(
        "all",
        {
            "previous": event(GameStatus.Final, "2026-05-12T02:10:00+00:00"),
            "current": event(GameStatus.InProgress, "2026-05-13T02:10:00+00:00"),
            "next": event(GameStatus.Scheduled, "2026-05-14T02:10:00+00:00"),
        },
    )

    assert [value.status_type for value in summary.values] == ["live", "scheduled"]


def test_sport_event_detail_icon_set_when_team_in_manifest(
    mocker: MockerFixture, make_manifest
) -> None:
    """Icons are populated from the manifest when the sport and team key are found."""
    mocker.patch(
        "merino.utils.logos.load_manifest",
        return_value=make_manifest(
            (LogoCategory.NHL, "phi"),
            (LogoCategory.NHL, "wpg"),
        ),
    )

    event = {
        "date": "2025-10-01T00:00:00+00:00",
        "sport": "NHL",
        "event_status": GameStatus.Scheduled,
        "home_team": {
            "key": "PHI",
            "name": "Philadelphia Flyers",
            "colors": ["D24303"],
        },
        "away_team": {"key": "WPG", "name": "Winnipeg Jets", "colors": ["041E42"]},
        "home_score": None,
        "away_score": None,
        "touched": "2025-10-01T00:00:00+00:00",
    }
    result = SportEventDetail.from_event_dict(event)

    host = f"https://{settings.image_gcs_v2.cdn_hostname}"
    assert str(result.home_team.icon) == f"{host}/logos/nhl/nhl_phi.png"
    assert str(result.away_team.icon) == f"{host}/logos/nhl/nhl_wpg.png"


def test_sport_event_detail_icon_none_for_unknown_sport() -> None:
    """Icons are None when the sport has no corresponding LogoCategory."""
    event = {
        "date": "2025-10-01T00:00:00+00:00",
        "sport": "TEST",
        "event_status": GameStatus.Scheduled,
        "home_team": {"key": "HOM", "name": "Home Team", "colors": ["000000"]},
        "away_team": {"key": "AWY", "name": "Away Team", "colors": ["FFFFFF"]},
        "home_score": None,
        "away_score": None,
        "touched": "2025-10-01T00:00:00+00:00",
    }
    result = SportEventDetail.from_event_dict(event)

    assert result.home_team.icon is None
    assert result.away_team.icon is None


def test_sport_event_detail_icon_set_for_fifa_uses_nations_logos(
    mocker: MockerFixture, make_manifest
) -> None:
    """FIFA events resolve to LogoCategory.Nations via SportLogoCategoryMap."""
    mocker.patch(
        "merino.utils.logos.load_manifest",
        return_value=make_manifest(
            (LogoCategory.Nations, "usa"),
            (LogoCategory.Nations, "can"),
        ),
    )

    event = {
        "date": "2026-06-15T00:00:00+00:00",
        "sport": "FIFA",
        "event_status": GameStatus.Scheduled,
        "home_team": {"key": "USA", "name": "United States", "colors": ["B22234"]},
        "away_team": {"key": "CAN", "name": "Canada", "colors": ["FF0000"]},
        "home_score": None,
        "away_score": None,
        "touched": "2026-06-15T00:00:00+00:00",
    }
    result = SportEventDetail.from_event_dict(event)

    host = f"https://{settings.image_gcs_v2.cdn_hostname}"
    assert str(result.home_team.icon) == f"{host}/logos/nations/nations_usa.png"
    assert str(result.away_team.icon) == f"{host}/logos/nations/nations_can.png"


def test_sport_event_detail_icon_none_when_team_not_in_manifest() -> None:
    """Icons are None when the team key is absent from the manifest."""
    event = {
        "date": "2025-10-01T00:00:00+00:00",
        "sport": "NHL",
        "event_status": GameStatus.Scheduled,
        "home_team": {"key": "ZZZ", "name": "Unknown Team", "colors": ["000000"]},
        "away_team": {"key": "YYY", "name": "Other Team", "colors": ["FFFFFF"]},
        "home_score": None,
        "away_score": None,
        "touched": "2025-10-01T00:00:00+00:00",
    }
    result = SportEventDetail.from_event_dict(event)

    assert result.home_team.icon is None
    assert result.away_team.icon is None


def test_sport_event_detail_fifa_icon_is_png_and_not_svg(
    mocker: MockerFixture,
) -> None:
    """The suggest request should return PNG icon instead of SVG."""
    manifest = LogoManifest(
        generated_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        lookups={
            LogoCategory.Nations: {
                "BRA": Logo(
                    name="BRA",
                    url="logos/nations/nations_br.png",
                    svg="logos/nations/svg/BRA.svg",
                ),
                "ARG": Logo(
                    name="ARG",
                    url="logos/nations/nations_ar.png",
                    svg="logos/nations/svg/ARG.svg",
                ),
            }
        },
    )
    mocker.patch("merino.utils.logos.load_manifest", return_value=manifest)

    event = {
        "date": "2026-06-15T00:00:00+00:00",
        "sport": "FIFA",
        "event_status": GameStatus.Scheduled,
        "home_team": {"key": "BRA", "name": "Brazil", "colors": ["#FFD600"]},
        "away_team": {"key": "ARG", "name": "Argentina", "colors": ["#74ACDF"]},
        "home_score": None,
        "away_score": None,
        "touched": "2026-06-15T00:00:00+00:00",
    }
    result = SportEventDetail.from_event_dict(event)

    assert str(result.home_team.icon).endswith("/logos/nations/nations_br.png")
    assert str(result.away_team.icon).endswith("/logos/nations/nations_ar.png")
