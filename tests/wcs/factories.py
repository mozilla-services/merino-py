"""Shared WCS provider fixtures."""

from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from merino.providers.suggest.sports.backends.sportsdata.common import GameStatus
from merino.providers.suggest.sports.backends.sportsdata.common.data import Event, Team
from merino.providers.suggest.sports.backends.sportsdata.common.wcs_elimination import (
    eliminated_team_keys,
)
from merino.providers.wcs.fake_data import get_all_teams
from merino.providers.wcs.provider import WcsProvider

ANCHOR = date(2026, 6, 15)
TEST_NOW = datetime(2026, 5, 13, 12, tzinfo=UTC)
KNOWN_TEAMS = [
    ("BRA", "Brazil"),
    ("ARG", "Argentina"),
    ("GER", "Germany"),
    ("FRA", "France"),
    ("ENG", "England"),
    ("USA", "United States"),
]


class StubWcsSport:
    """Small WCS sport stand-in that behaves like the Redis-backed sport."""

    def __init__(
        self,
        events: list[Event],
        teams: list[Team],
        cached_eliminated_team_keys: set[str] | None = None,
    ) -> None:
        self.events = events
        self.teams = teams
        self.cached_eliminated_team_keys = (
            eliminated_team_keys(events)
            if cached_eliminated_team_keys is None
            else cached_eliminated_team_keys
        )

    async def get_events_by_date(
        self, start: datetime | None = None, end: datetime | None = None
    ) -> list[Event]:
        """Return events in the requested inclusive datetime range."""
        return [
            event
            for event in self.events
            if (start is None or event.date >= start) and (end is None or event.date <= end)
        ]

    async def get_all_teams(self) -> dict[int, Team]:
        """Return cached teams by global team ID."""
        return {team.id: team for team in self.teams}

    async def get_eliminated_team_keys(self) -> set[str]:
        """Return cached eliminated WCS team keys."""
        return self.cached_eliminated_team_keys


def team_dict(key: str, name: str, team_id: int) -> dict[str, Any]:
    """Build the compact team shape stored on cached events."""
    return {
        "key": key,
        "id": team_id,
        "name": name,
        "region": key,
        "colors": ["Blue", "White"],
    }


def event(
    event_id: int,
    day_offset: int,
    hour: int,
    home: tuple[str, str, int],
    away: tuple[str, str, int],
    status: GameStatus,
    *,
    home_score: int | None = None,
    away_score: int | None = None,
    home_extra: int | None = None,
    away_extra: int | None = None,
    home_penalty: int | None = None,
    away_penalty: int | None = None,
    period: str | None = None,
    clock: str | None = None,
    stage: str | None = None,
    original_date: str | None = None,
    round_id: int | None = None,
    season_type: int | None = None,
    group: str | None = None,
    winner: str | None = None,
    is_closed: bool | None = None,
) -> Event:
    """Build a cached event model."""
    event_date = datetime.combine(ANCHOR + timedelta(days=day_offset), time(hour, tzinfo=UTC))
    return Event(
        sport="fifa",
        id=event_id,
        terms=f"{home[1].lower()} {away[1].lower()}",
        date=event_date,
        original_date=original_date or event_date.isoformat(),
        home_team=team_dict(*home),
        away_team=team_dict(*away),
        home_score=home_score,
        away_score=away_score,
        status=status,
        expiry=event_date + timedelta(days=90),
        updated=event_date - timedelta(minutes=5),
        period=period,
        home_extra=home_extra,
        away_extra=away_extra,
        home_penalty=home_penalty,
        away_penalty=away_penalty,
        clock=clock,
        stage=stage,
        round_id=round_id,
        season_type=season_type,
        group=group,
        winner=winner,
        is_closed=is_closed,
    )


def build_events() -> list[Event]:
    """Build the deterministic event set used by WCS provider tests."""
    bra, arg, ger, fra, eng, usa = [
        (key, name, 90000000 + index) for index, (key, name) in enumerate(KNOWN_TEAMS, start=1)
    ]
    return [
        event(1001, -1, 14, bra, arg, GameStatus.Final, home_score=2, away_score=1, period="FT"),
        event(
            1002,
            -1,
            18,
            ger,
            fra,
            GameStatus.Final,
            home_score=1,
            away_score=1,
            home_extra=1,
            away_extra=1,
            home_penalty=5,
            away_penalty=4,
            period="FT(P)",
            clock="120",
        ),
        event(
            1003,
            0,
            14,
            eng,
            usa,
            GameStatus.InProgress,
            home_score=1,
            away_score=0,
            period="2",
            clock="67",
        ),
        event(
            1004,
            0,
            17,
            bra,
            ger,
            GameStatus.InProgress,
            home_score=2,
            away_score=2,
            period="ET",
            clock="90+15",
        ),
        event(1005, 1, 15, arg, eng, GameStatus.Scheduled, period="1", clock="0"),
        event(1006, 1, 19, fra, usa, GameStatus.Scheduled, period="1", clock="0"),
        event(1007, 8, 19, fra, usa, GameStatus.Scheduled),
    ]


def build_teams() -> list[Team]:
    """Build deterministic cached teams from the tournament roster."""
    teams = []
    for roster_team in get_all_teams():
        teams.append(
            Team(
                name=roster_team.name,
                aliases=[roster_team.name],
                terms=roster_team.name.lower(),
                fullname=roster_team.name,
                key=roster_team.key,
                locale=roster_team.region,
                id=roster_team.global_team_id,
                colors=[],
                updated=TEST_NOW,
                expiry=TEST_NOW + timedelta(days=90),
                country=roster_team.region,
            )
        )
    return teams


def build_provider(
    events: list[Event] | None = None,
    teams: list[Team] | None = None,
    metrics_client: Any | None = None,
    eliminated_team_keys: set[str] | None = None,
) -> WcsProvider:
    """Build a WCS provider backed by deterministic stub data."""
    stub_events = build_events() if events is None else events
    stub_teams = build_teams() if teams is None else teams
    return WcsProvider(
        sport=StubWcsSport(stub_events, stub_teams, eliminated_team_keys),
        metrics_client=metrics_client,
    )
