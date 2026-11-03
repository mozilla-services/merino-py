# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the Wrexham widget mock data."""

from datetime import UTC, datetime

from merino.providers.widgets.wrexham.mock_data import build_mock_matches, build_mock_standings
from merino.providers.widgets.wrexham.protocol import (
    CHAMPIONSHIP,
    FA_CUP,
    WREXHAM_TEAM_ID,
    Match,
    MatchPeriod,
    MatchStatus,
)

NOW = datetime(2026, 11, 2, 15, 30, tzinfo=UTC)


def _involves_wrexham(match: Match) -> bool:
    return WREXHAM_TEAM_ID in (match.home_team.id, match.away_team.id)


def test_matches_are_grouped_relative_to_now() -> None:
    """Previous matches kicked off before now, upcoming ones kick off after."""
    matches = build_mock_matches(NOW)

    assert all(match.kickoff < NOW for match in matches.previous + matches.current)
    assert all(match.kickoff > NOW for match in matches.upcoming)


def test_matches_are_ordered_as_in_the_contract() -> None:
    """Previous matches are newest first and upcoming matches earliest first."""
    matches = build_mock_matches(NOW)

    previous_kickoffs = [match.kickoff for match in matches.previous]
    upcoming_kickoffs = [match.kickoff for match in matches.upcoming]

    assert previous_kickoffs == sorted(previous_kickoffs, reverse=True)
    assert upcoming_kickoffs == sorted(upcoming_kickoffs)


def test_matches_all_involve_wrexham_and_cover_both_competitions() -> None:
    """Every match involves Wrexham, across the Championship and the FA Cup."""
    matches = build_mock_matches(NOW)
    all_matches = matches.previous + matches.current + matches.upcoming

    assert all(_involves_wrexham(match) for match in all_matches)
    assert {match.competition.id for match in all_matches} == {CHAMPIONSHIP.id, FA_CUP.id}


def test_matches_have_unique_ids() -> None:
    """Each mock match has its own ID."""
    matches = build_mock_matches(NOW)
    ids = [match.id for match in matches.previous + matches.current + matches.upcoming]

    assert len(ids) == len(set(ids))


def test_matches_cover_a_range_of_states() -> None:
    """Groups hold the statuses the contract assigns them, with a range of states covered."""
    matches = build_mock_matches(NOW)

    assert {match.status for match in matches.previous} == {
        MatchStatus.Final,
        MatchStatus.Canceled,
    }
    assert {match.status for match in matches.current} == {MatchStatus.InProgress}
    assert {match.status for match in matches.upcoming} == {
        MatchStatus.Scheduled,
        MatchStatus.Postponed,
    }
    assert {match.period for match in matches.previous} == {
        MatchPeriod.Regular,
        MatchPeriod.ExtraTime,
        MatchPeriod.PenaltyShootout,
        None,
    }


def test_matches_follow_field_rules() -> None:
    """Fields that only apply once a match starts are null for matches that haven't."""
    matches = build_mock_matches(NOW)

    for match in matches.previous + matches.current + matches.upcoming:
        started = match.status not in (
            MatchStatus.Scheduled,
            MatchStatus.Postponed,
            MatchStatus.Canceled,
        )
        assert (match.period is not None) == started
        assert (match.home_score is not None) == started
        assert (match.away_score is not None) == started
        assert (match.clock is not None) == (match.status == MatchStatus.InProgress)
        has_shootout = match.period == MatchPeriod.PenaltyShootout
        assert (match.home_penalty_score is not None) == has_shootout
        assert (match.away_penalty_score is not None) == has_shootout


def test_match_logo_urls_point_at_soccer_crests() -> None:
    """Team logo URLs point at the soccer crests uploaded to the image CDN."""
    match = build_mock_matches(NOW).current[0]

    assert str(match.away_team.logo_url).endswith(f"/logos/soccer/soccer_{WREXHAM_TEAM_ID}.png")


def test_standings_are_a_full_ordered_table() -> None:
    """The table has 24 rows ordered by position, with points not increasing."""
    standings = build_mock_standings()

    assert standings.competition == CHAMPIONSHIP
    assert [row.position for row in standings.standings] == list(range(1, 25))

    points = [row.points for row in standings.standings]
    assert points == sorted(points, reverse=True)


def test_standings_use_abbreviated_names() -> None:
    """Standings use abbreviated team names, e.g. 'Wrexham' rather than 'Wrexham AFC'."""
    standings = build_mock_standings()
    wrexham = next(row for row in standings.standings if row.team.id == WREXHAM_TEAM_ID)

    assert wrexham.team.name == "Wrexham"
