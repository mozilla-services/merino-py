"""Shared WCS provider fixtures."""

from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from merino.providers.suggest.sports.backends.sportsdata.common import GameStatus
from merino.providers.suggest.sports.backends.sportsdata.common.data import Event
from merino.providers.wcs.provider import WcsProvider

ANCHOR = date(2026, 6, 15)
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

    def __init__(self, events: list[Event]) -> None:
        self.events = events

    async def get_events_by_date(
        self, start: datetime | None = None, end: datetime | None = None
    ) -> list[Event]:
        """Return events in the requested inclusive datetime range."""
        return [
            event
            for event in self.events
            if (start is None or event.date >= start) and (end is None or event.date <= end)
        ]


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


def build_provider(
    events: list[Event] | None = None,
    metrics_client: Any | None = None,
) -> WcsProvider:
    """Build a WCS provider backed by deterministic stub data."""
    stub_events = build_events() if events is None else events
    return WcsProvider(
        sport=StubWcsSport(stub_events),
        metrics_client=metrics_client,
    )
