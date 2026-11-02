"""Response models for the Wrexham widget endpoints."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, HttpUrl


class MatchStatus(StrEnum):
    """Match status, normalized from SportsDataIO."""

    Scheduled = "Scheduled"
    InProgress = "InProgress"
    Break = "Break"
    Final = "Final"
    Postponed = "Postponed"
    Canceled = "Canceled"
    Suspended = "Suspended"
    Delayed = "Delayed"
    Unknown = "Unknown"


class MatchPeriod(StrEnum):
    """Phase of play. During play it is the current phase; after completion, the final one."""

    Regular = "Regular"
    ExtraTime = "ExtraTime"
    PenaltyShootout = "PenaltyShootout"


class Competition(BaseModel):
    """A competition a match belongs to."""

    id: int = Field(description="SportsDataIO competition ID.")
    name: str = Field(description="Competition name.")


class Team(BaseModel):
    """A team taking part in a match or listed in the standings."""

    id: int = Field(description="SportsDataIO global team ID.")
    name: str = Field(description="Team name.")
    logo_url: HttpUrl = Field(description="URL of the team crest, or of a fallback image.")


class Match(BaseModel):
    """A Wrexham match."""

    id: int = Field(description="Unique match identifier.")
    competition: Competition = Field(description="Competition the match belongs to.")
    kickoff: datetime = Field(description="Latest scheduled kickoff time, in UTC.")
    home_team: Team = Field(description="Home team.")
    away_team: Team = Field(description="Away team.")
    period: MatchPeriod | None = Field(
        description="Current phase during play, final phase after completion. "
        "Null before the match begins."
    )
    status: MatchStatus = Field(description="Match status.")
    clock: str | None = Field(
        description="Elapsed minutes including stoppage time, e.g. '67' or '90+3'. "
        "Null when the match is not live."
    )
    home_score: int | None = Field(
        description="Home goals including extra time, excluding the penalty shootout. "
        "Null before the match begins."
    )
    away_score: int | None = Field(
        description="Away goals including extra time, excluding the penalty shootout. "
        "Null before the match begins."
    )
    home_penalty_score: int | None = Field(
        description="Home penalty shootout goals. Null when not applicable."
    )
    away_penalty_score: int | None = Field(
        description="Away penalty shootout goals. Null when not applicable."
    )
    updated_at: datetime = Field(description="Time the match data was last updated, in UTC.")


class MatchesResponse(BaseModel):
    """Response for the matches endpoint."""

    previous: list[Match] = Field(description="Completed or cancelled matches, newest first.")
    current: list[Match] = Field(
        description="Matches in progress, on a break, delayed or suspended."
    )
    upcoming: list[Match] = Field(description="Scheduled or postponed matches, earliest first.")


class Standing(BaseModel):
    """A row in the league table."""

    position: int = Field(ge=0, description="Overall league position.")
    team: Team = Field(description="Team, with its abbreviated name.")
    played: int = Field(ge=0, description="Number of matches played.")
    goal_difference: int = Field(description="Goals scored minus goals conceded.")
    points: int = Field(description="League points. Can be negative after a points deduction.")


class StandingsResponse(BaseModel):
    """Response for the standings endpoint."""

    competition: Competition = Field(description="Competition the table belongs to.")
    standings: list[Standing] = Field(
        description="Table rows ordered by position. Empty when no table is available yet."
    )
