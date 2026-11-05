"""Mock data for the Wrexham widget endpoints.

Kickoff times are relative to the request time, so results are always in the past and
fixtures always in the future.
"""

from datetime import datetime, timedelta
from urllib.parse import urljoin

from pydantic import HttpUrl

from merino.providers.widgets.wrexham.protocol import (
    Competition,
    Match,
    MatchesResponse,
    MatchPeriod,
    MatchStatus,
    Standing,
    StandingsResponse,
    Team,
)
from merino.providers.widgets.wrexham.sportsdata import (
    CHAMPIONSHIP,
    FA_CUP,
    WREXHAM_TEAM_ID,
)
from merino.utils.logos import CDN_ROOT_URL

# Global team ID -> (full name, abbreviated name).
_TEAMS: dict[int, tuple[str, str]] = {
    90000523: ("Swansea City AFC", "Swansea"),
    90000973: ("Middlesbrough FC", "Middlesbrough"),
    90000527: ("West Ham United FC", "West Ham"),
    90000521: ("Stoke City FC", "Stoke City"),
    90001463: ("Wolverhampton Wanderers FC", "Wolves"),
    90002219: ("Queens Park Rangers FC", "QPR"),
    90001988: ("Birmingham City FC", "Birmingham"),
    90002179: ("Millwall FC", "Millwall"),
    90000526: ("West Bromwich Albion FC", "West Brom"),
    WREXHAM_TEAM_ID: ("Wrexham AFC", "Wrexham"),
    90002009: ("Bristol City FC", "Bristol City"),
    90000520: ("Southampton FC", "Southampton"),
    90002026: ("Charlton Athletic FC", "Charlton Athletic"),
    90001990: ("Blackburn Rovers FC", "Blackburn Rovers"),
    90001540: ("Sheffield United FC", "Sheffield United"),
    90002153: ("Lincoln City FC", "Lincoln City"),
    90001997: ("Bolton Wanderers FC", "Bolton Wanderers"),
    90000519: ("Norwich City FC", "Norwich City"),
    90002214: ("Portsmouth FC", "Portsmouth"),
    90000525: ("Watford FC", "Watford"),
    90001461: ("Cardiff City FC", "Cardiff City"),
    90000857: ("Burnley FC", "Burnley"),
    90002059: ("Derby County FC", "Derby County"),
    90002217: ("Preston North End FC", "Preston North End"),
    # FA Cup opponents outside the Championship.
    90002267: ("Stockport County FC", "Stockport County"),
    90001968: ("Barnsley FC", "Barnsley"),
    90002225: ("Reading FC", "Reading"),
}

# (team ID, goal difference, points) in league position order, 14 matches played each.
_TABLE: list[tuple[int, int, int]] = [
    (90000523, 12, 30),
    (90000973, 10, 28),
    (90000527, 8, 27),
    (90000521, 7, 25),
    (90001463, 6, 24),
    (90002219, 5, 23),
    (90001988, 4, 22),
    (90002179, 3, 21),
    (90000526, 2, 21),
    (WREXHAM_TEAM_ID, 2, 20),
    (90002009, 1, 20),
    (90000520, 0, 19),
    (90002026, -1, 19),
    (90001990, -1, 18),
    (90001540, -2, 18),
    (90002153, -3, 17),
    (90001997, -3, 16),
    (90000519, -4, 16),
    (90002214, -5, 15),
    (90000525, -6, 14),
    (90001461, -7, 13),
    (90000857, -8, 12),
    (90002059, -10, 10),
    (90002217, -12, 8),
]


def _logo_url(team_id: int) -> HttpUrl:
    """Return the CDN URL of a team crest uploaded to the image bucket."""
    return HttpUrl(urljoin(CDN_ROOT_URL, f"logos/soccer/soccer_{team_id}.png"))


def _team(team_id: int, short_name: bool = False) -> Team:
    """Build a team with its full or abbreviated name."""
    full_name, abbreviated_name = _TEAMS[team_id]
    return Team(
        id=team_id,
        name=abbreviated_name if short_name else full_name,
        logo_url=_logo_url(team_id),
    )


def _match(
    match_id: int,
    competition: Competition,
    kickoff: datetime,
    home_team_id: int,
    away_team_id: int,
    status: MatchStatus,
    updated_at: datetime,
    period: MatchPeriod | None = None,
    clock: str | None = None,
    score: tuple[int, int] | None = None,
    penalty_score: tuple[int, int] | None = None,
) -> Match:
    """Build a mock match."""
    home_score, away_score = score if score else (None, None)
    home_penalty_score, away_penalty_score = penalty_score if penalty_score else (None, None)
    return Match(
        id=match_id,
        competition=competition,
        kickoff=kickoff,
        home_team=_team(home_team_id),
        away_team=_team(away_team_id),
        period=period,
        status=status,
        clock=clock,
        home_score=home_score,
        away_score=away_score,
        home_penalty_score=home_penalty_score,
        away_penalty_score=away_penalty_score,
        updated_at=updated_at,
    )


def build_mock_matches(now: datetime) -> MatchesResponse:
    """Return mock matches covering a range of match states, relative to `now`.

    `previous` is newest first and `upcoming` earliest first, as in the API contract.
    """
    base = now.replace(minute=0, second=0, microsecond=0)

    def days_ago(days: int) -> datetime:
        return base - timedelta(days=days)

    def days_ahead(days: int) -> datetime:
        return base + timedelta(days=days)

    def full_time(kickoff: datetime) -> datetime:
        return kickoff + timedelta(hours=2)

    previous = [
        _match(
            116350,
            CHAMPIONSHIP,
            days_ago(3),
            WREXHAM_TEAM_ID,
            90002009,
            MatchStatus.Final,
            full_time(days_ago(3)),
            MatchPeriod.Regular,
            score=(2, 1),
        ),
        _match(
            116349,
            FA_CUP,
            days_ago(7),
            WREXHAM_TEAM_ID,
            90002267,
            MatchStatus.Final,
            full_time(days_ago(7)),
            MatchPeriod.PenaltyShootout,
            score=(1, 1),
            penalty_score=(4, 3),
        ),
        _match(
            116348,
            FA_CUP,
            days_ago(10),
            90001968,
            WREXHAM_TEAM_ID,
            MatchStatus.Final,
            full_time(days_ago(10)),
            MatchPeriod.ExtraTime,
            score=(1, 2),
        ),
        _match(
            116347,
            CHAMPIONSHIP,
            days_ago(14),
            WREXHAM_TEAM_ID,
            90002059,
            MatchStatus.Canceled,
            days_ago(14),
        ),
        _match(
            116346,
            CHAMPIONSHIP,
            days_ago(17),
            90002179,
            WREXHAM_TEAM_ID,
            MatchStatus.Final,
            full_time(days_ago(17)),
            MatchPeriod.Regular,
            score=(0, 0),
        ),
        _match(
            116345,
            CHAMPIONSHIP,
            days_ago(21),
            WREXHAM_TEAM_ID,
            90000525,
            MatchStatus.Final,
            full_time(days_ago(21)),
            MatchPeriod.Regular,
            score=(3, 1),
        ),
    ]

    current = [
        _match(
            116351,
            CHAMPIONSHIP,
            now - timedelta(minutes=110),
            90002059,
            WREXHAM_TEAM_ID,
            MatchStatus.InProgress,
            now,
            MatchPeriod.Regular,
            clock="90+3",
            score=(1, 1),
        ),
    ]

    upcoming = [
        _match(
            116352,
            CHAMPIONSHIP,
            days_ahead(3),
            WREXHAM_TEAM_ID,
            90000523,
            MatchStatus.Scheduled,
            now,
        ),
        _match(
            116353,
            CHAMPIONSHIP,
            days_ahead(6),
            90001540,
            WREXHAM_TEAM_ID,
            MatchStatus.Postponed,
            now,
        ),
        _match(
            116354,
            FA_CUP,
            days_ahead(10),
            WREXHAM_TEAM_ID,
            90002225,
            MatchStatus.Scheduled,
            now,
        ),
        _match(
            116355,
            CHAMPIONSHIP,
            days_ahead(14),
            90000519,
            WREXHAM_TEAM_ID,
            MatchStatus.Scheduled,
            now,
        ),
        _match(
            116356,
            CHAMPIONSHIP,
            days_ahead(17),
            WREXHAM_TEAM_ID,
            90002214,
            MatchStatus.Scheduled,
            now,
        ),
        _match(
            116357,
            CHAMPIONSHIP,
            days_ahead(21),
            90001461,
            WREXHAM_TEAM_ID,
            MatchStatus.Scheduled,
            now,
        ),
    ]

    return MatchesResponse(previous=previous, current=current, upcoming=upcoming)


def build_mock_standings() -> StandingsResponse:
    """Return a mock EFL Championship table, with abbreviated team names."""
    return StandingsResponse(
        competition=CHAMPIONSHIP,
        standings=[
            Standing(
                position=position,
                team=_team(team_id, short_name=True),
                played=14,
                goal_difference=goal_difference,
                points=points,
            )
            for position, (team_id, goal_difference, points) in enumerate(_TABLE, start=1)
        ],
    )
