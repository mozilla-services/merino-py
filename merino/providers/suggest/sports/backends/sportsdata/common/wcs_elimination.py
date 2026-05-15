"""WCS tournament elimination helpers."""

from collections.abc import Iterable
import json
from importlib.resources import files

import orjson

from merino.providers.suggest.sports.backends.sportsdata.common.data import Event

_FIRST_KNOCKOUT_ADVANCER_COUNT = 32
_ELIMINATED_TEAM_KEYS_META_KEY = "meta:eliminated_team_keys"
_PLACEHOLDER_TEAM_KEYS = {"TBD"}


def eliminated_team_keys_cache_key(cache_prefix: str) -> str:
    """Return the Redis key used for cached eliminated WCS team keys."""
    return f"{cache_prefix}:{_ELIMINATED_TEAM_KEYS_META_KEY}"


def serialize_eliminated_team_keys(team_keys: Iterable[str]) -> bytes:
    """Serialize eliminated team keys for Redis."""
    return orjson.dumps(sorted(set(team_keys)))


def parse_eliminated_team_keys(raw: bytes | str | None) -> set[str]:
    """Parse cached eliminated team keys."""
    if not raw:
        return set()
    payload = orjson.loads(raw)
    if not isinstance(payload, list) or not all(isinstance(key, str) for key in payload):
        raise ValueError("cached eliminated team keys must be a JSON list of strings")
    return set(payload)


def eliminated_team_keys(events: Iterable[Event]) -> set[str]:
    """Return team keys eliminated according to cached WCS schedule state."""
    event_list = list(events)
    eliminated = _group_stage_eliminated_team_keys(event_list)

    for event in event_list:
        if not _is_completed_knockout_event(event):
            continue
        winner_key = _winner_key(event)
        if winner_key is None:
            continue
        for team_key in _event_team_keys(event):
            if team_key != winner_key:
                eliminated.add(team_key)

    eliminated.difference_update(_active_path_team_keys(event_list))
    return eliminated


def _group_stage_eliminated_team_keys(events: list[Event]) -> set[str]:
    """Return group-stage non-advancers once the first knockout round is populated."""
    first_knockout_round = _first_knockout_round_id(events)
    if first_knockout_round is None:
        return set()

    advancing_keys = {
        key
        for event in events
        if event.round_id == first_knockout_round
        for key in _event_team_keys(event)
    }
    if len(advancing_keys) < _FIRST_KNOCKOUT_ADVANCER_COUNT:
        return set()

    return _roster_team_keys() - advancing_keys


def _first_knockout_round_id(events: list[Event]) -> int | None:
    """Return the first populated knockout round id from cached events."""
    round_ids = [
        event.round_id
        for event in events
        if _is_knockout_event(event) and event.round_id is not None and _event_team_keys(event)
    ]
    return min(round_ids) if round_ids else None


def _is_completed_knockout_event(event: Event) -> bool:
    """Return True when `event` can eliminate its loser."""
    return _is_knockout_event(event) and (event.status.is_final() or bool(event.is_closed))


def _is_knockout_event(event: Event) -> bool:
    """Return True for WCS knockout-stage events."""
    return event.season_type == 3 and event.group is None


def _active_path_team_keys(events: list[Event]) -> set[str]:
    """Return team keys with a scheduled or live knockout event still ahead."""
    return {
        key
        for event in events
        if _is_knockout_event(event)
        and (event.status.is_scheduled() or event.status.is_in_progress())
        for key in _event_team_keys(event)
    }


def _event_team_keys(event: Event) -> set[str]:
    """Return real, non-empty team keys from an event."""
    return {
        key
        for key in (
            event.home_team.get("key"),
            event.away_team.get("key"),
        )
        if isinstance(key, str) and key and key not in _PLACEHOLDER_TEAM_KEYS
    }


def _winner_key(event: Event) -> str | None:
    """Return the winning team key only when SportsData declares one."""
    winner = (event.winner or "").lower()
    if winner == "hometeam":
        return _team_key(event.home_team)
    if winner == "awayteam":
        return _team_key(event.away_team)
    return None


def _team_key(team: dict[str, object]) -> str | None:
    """Return a team key from a compact event team dictionary."""
    key = team.get("key")
    return key if isinstance(key, str) and key else None


def _roster_team_keys() -> set[str]:
    """Return tournament roster team keys from static WCS metadata.

    This is only used while materializing eliminated-team metadata during the WCS
    cache refresh; endpoint requests read the cached metadata instead.
    """
    data = json.loads((files("merino.data") / "wcs_teams.json").read_text())
    return {str(team["Key"]) for team in data}
