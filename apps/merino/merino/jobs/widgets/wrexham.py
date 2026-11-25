"""Long-running job that ingests Wrexham fixtures, live matches and standings from SportsDataIO
into the widgets Redis instance.

Meant to run as a long-lived pod: `merino-jobs wrexham run-loop`.
"""

import asyncio
import logging
import signal
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from time import monotonic, perf_counter

import typer
from pydantic import HttpUrl

from merino.cache.redis import RedisAdapter, create_redis_clients
from merino.configs import settings
from merino.providers.widgets.wrexham import metrics
from merino.providers.widgets.wrexham.protocol import CHAMPIONSHIP, FA_CUP, Match, Team
from merino.providers.widgets.wrexham.sportsdata import SportsDataBackend
from merino.providers.widgets.wrexham.store import WrexhamStore
from merino_common.utils.http_client import create_http_client

logger = logging.getLogger(__name__)

match_changes_logger = logging.getLogger(f"{__name__}.match_changes")

# Competitions to ingest fixtures and live matches for. Standings are Championship only.
COMPETITIONS = [CHAMPIONSHIP, FA_CUP]

# Live match fields that are logged when they change.
TRACKED_MATCH_FIELDS = (
    "status",
    "period",
    "home_score",
    "away_score",
    "home_penalty_score",
    "away_penalty_score",
)

MatchState = dict[str, object]

# Short name for each 2026-27 EFL Championship team, by global team ID. SportsDataIO only
# provides short names in the standings, so these are used until the job has fetched them,
# e.g. right after it starts. Update them each summer, along with the `season` setting.
TEAM_SHORT_NAMES: dict[int, str] = {
    90000519: "Norwich",
    90000520: "Southampton",
    90000521: "Stoke",
    90000523: "Swansea",
    90000525: "Watford",
    90000526: "West Brom",
    90000527: "West Ham",
    90000857: "Burnley",
    90000973: "Middlesbrough",
    90001461: "Cardiff",
    90001463: "Wolverhampton",
    90001540: "Sheffield Utd",
    90001988: "Birmingham",
    90001990: "Blackburn",
    90001997: "Bolton",
    90002009: "Bristol City",
    90002026: "Charlton Athl.",
    90002059: "Derby County",
    90002153: "Lincoln City",
    90002179: "Millwall",
    90002214: "Portsmouth",
    90002217: "Preston NE",
    90002219: "QPR",
    90002327: "Wrexham",
}


def use_short_names(matches: list[Match], short_names: dict[int, str]) -> list[Match]:
    """Replace each team's name with its short name, for teams in `short_names`.

    Teams without a short name, e.g. FA Cup opponents from outside the Championship, keep
    their full name.
    """

    def with_short_name(team: Team) -> Team:
        short_name = short_names.get(team.id)
        return team if short_name is None else team.model_copy(update={"name": short_name})

    return [
        match.model_copy(
            update={
                "home_team": with_short_name(match.home_team),
                "away_team": with_short_name(match.away_team),
            }
        )
        for match in matches
    ]


def _log_value(value: object) -> object:
    """Return a match field as a plain value for logging, e.g. an enum as its string."""
    return str(value) if isinstance(value, StrEnum) else value


class WrexhamRefreshError(Exception):
    """Raised when a refresh fails for some, but not necessarily all, of its data."""


class WrexhamIngester:
    """Refreshes Wrexham data from SportsDataIO into the store.

    Live matches are refreshed on every run. Fixtures and standings are refreshed only when
    their interval has passed since their last successful refresh. A failed refresh is retried
    on the next run.
    """

    backend: SportsDataBackend
    store: WrexhamStore
    season: int
    fixtures_interval: timedelta
    standings_interval: timedelta
    _fixtures_due_at: float
    _standings_due_at: float
    _short_names: dict[int, str]
    _match_states: dict[int, MatchState]

    def __init__(
        self,
        backend: SportsDataBackend,
        store: WrexhamStore,
        season: int,
        fixtures_interval: timedelta,
        standings_interval: timedelta,
    ) -> None:
        self.backend = backend
        self.store = store
        self.season = season
        self.fixtures_interval = fixtures_interval
        self.standings_interval = standings_interval
        # Due on the first run.
        self._fixtures_due_at = float("-inf")
        self._standings_due_at = float("-inf")
        # Updated from the standings on each standings refresh.
        self._short_names = dict(TEAM_SHORT_NAMES)
        # The last logged state of each live match, by match ID.
        self._match_states = {}

    async def refresh_fixtures(self) -> None:
        """Write the season's Wrexham fixtures for each competition.

        Each competition is written independently: a failure in one doesn't stop the others.

        Raises:
            - `WrexhamRefreshError` after trying every competition, if any of them failed,
            so the refresh is retried.
        """
        failed_ids: list[int] = []
        for competition in COMPETITIONS:
            try:
                matches = await self.backend.fetch_schedule(competition, self.season)
                matches = use_short_names(matches, self._short_names)
                await self.store.write_fixtures(competition.id, matches)
                logger.info(
                    "Refreshed Wrexham fixtures",
                    extra={
                        "refresh": "fixtures",
                        "competition_id": competition.id,
                        "match_count": len(matches),
                    },
                )
            except Exception as ex:
                failed_ids.append(competition.id)
                logger.error(
                    "Failed to refresh Wrexham fixtures",
                    extra={
                        "refresh": "fixtures",
                        "competition_id": competition.id,
                        "error": str(ex),
                    },
                )
        if failed_ids:
            raise WrexhamRefreshError(f"Failed to refresh fixtures for competitions {failed_ids}")

    async def refresh_live_matches(self) -> None:
        """Write today's Wrexham matches across all competitions, earliest kickoff first.

        If any competition fails, nothing is written, so a partial list never replaces a
        complete one. The stored list stays until it expires.
        """
        matches: list[Match] = []
        for competition in COMPETITIONS:
            matches.extend(await self.backend.fetch_live_matches(competition))
        matches = use_short_names(matches, self._short_names)
        await self.store.write_live_matches(sorted(matches, key=lambda match: match.kickoff))
        self._log_match_changes(matches)
        logger.info(
            "Refreshed Wrexham live matches",
            extra={
                "refresh": "live_matches",
                "match_count": len(matches),
                "statuses": sorted({match.status for match in matches}),
            },
        )

    def _log_match_changes(self, matches: list[Match]) -> None:
        """Log each live match that's new or whose tracked fields changed since the last live
        refresh.

        A match is logged in full the first time it's seen, e.g. at the start of a match day or
        after the job restarts. Matches no longer in the live data are forgotten.
        """
        states: dict[int, MatchState] = {}
        for match in matches:
            state = {field: getattr(match, field) for field in TRACKED_MATCH_FIELDS}
            states[match.id] = state
            previous = self._match_states.get(match.id)
            if previous == state:
                continue

            changed_fields = (
                [field for field in TRACKED_MATCH_FIELDS if previous[field] != state[field]]
                if previous is not None
                else []
            )
            match_changes_logger.info(
                "Wrexham match changed",
                extra={
                    "match_id": match.id,
                    "competition": match.competition.name,
                    "home_team": match.home_team.name,
                    "away_team": match.away_team.name,
                    "kickoff": match.kickoff.isoformat(),
                    "updated_at": match.updated_at.isoformat(),
                    "first_seen": previous is None,
                    "changed_fields": changed_fields,
                    "clock": match.clock,
                    **{field: _log_value(value) for field, value in state.items()},
                },
            )
        self._match_states = states

    async def refresh_standings(self) -> None:
        """Write the Championship table, and use its short team names for later matches.

        Teams from `TEAM_SHORT_NAMES` that aren't in the table, e.g. relegated last season,
        keep their short names.
        """
        standings = await self.backend.fetch_standings(CHAMPIONSHIP, self.season)
        await self.store.write_standings(standings)
        self._short_names = TEAM_SHORT_NAMES | {row.team.id: row.team.name for row in standings}
        logger.info(
            "Refreshed Wrexham standings",
            extra={"refresh": "standings", "team_count": len(standings)},
        )

    async def run_once(self) -> None:
        """Run the refreshes that are due. A failed refresh is logged and doesn't stop the
        others. Fixtures and standings are next due an interval after they succeed, or on the
        next run if they fail.

        Each refresh records its result, duration and, on success, sync time, tagged by data
        type ("live_matches", "fixtures" or "standings").
        """
        now = monotonic()

        def set_fixtures_due() -> None:
            self._fixtures_due_at = now + self.fixtures_interval.total_seconds()

        def set_standings_due() -> None:
            self._standings_due_at = now + self.standings_interval.total_seconds()

        refreshes: list[tuple[str, Callable[[], Awaitable[None]], Callable[[], None] | None]] = [
            ("live_matches", self.refresh_live_matches, None)
        ]
        if now >= self._fixtures_due_at:
            refreshes.append(("fixtures", self.refresh_fixtures, set_fixtures_due))
        if now >= self._standings_due_at:
            refreshes.append(("standings", self.refresh_standings, set_standings_due))

        for data_type, refresh, on_success in refreshes:
            await self._run_refresh(data_type, refresh, on_success)

    @staticmethod
    async def _run_refresh(
        data_type: str,
        refresh: Callable[[], Awaitable[None]],
        on_success: Callable[[], None] | None,
    ) -> None:
        """Run a refresh, log a failure and record its metrics."""
        attributes = {"data_type": data_type}
        start = perf_counter()
        # Kept if refresh() raises a BaseException, e.g. CancelledError or KeyboardInterrupt
        result = "canceled"
        try:
            await refresh()
        except Exception as ex:
            result = "failure"
            logger.error("Wrexham refresh failed", extra={"refresh": data_type, "error": str(ex)})
        else:
            result = "success"
            metrics.job_last_synced_at.set(datetime.now(UTC).timestamp(), attributes)
            if on_success is not None:
                on_success()
        finally:
            metrics.job_refresh_duration.record(perf_counter() - start, attributes)
            metrics.job_refresh_count.add(1, {**attributes, "result": result})

    async def run_loop(self, interval_sec: float, stop_event: asyncio.Event) -> None:
        """Run the refreshes every `interval_sec` until `stop_event` is set."""
        while not stop_event.is_set():
            await self.run_once()
            # Wake immediately on a stop signal rather than sleeping out the interval.
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=interval_sec)
            except TimeoutError:
                pass

    async def shutdown(self) -> None:
        """Close the SportsDataIO and Redis connections."""
        await self.backend.shutdown()
        await self.store.cache.close()


def _build_ingester() -> WrexhamIngester:  # pragma: no cover
    """Build the ingester from settings."""
    wrexham = settings.widgets.providers.wrexham
    backend = SportsDataBackend(
        http_client=create_http_client(
            base_url=wrexham.sportsdata.url_base,
            connect_timeout=wrexham.sportsdata.connect_timeout_sec,
            request_timeout=wrexham.sportsdata.request_timeout_sec,
        ),
        api_key=settings.providers.sports.sportsdata.api_key,
        fallback_logo_url=HttpUrl(wrexham.fallback_logo_url),
    )
    store = WrexhamStore(
        cache=RedisAdapter(
            *create_redis_clients(
                settings.redis.widgets_server,
                settings.redis.widgets_replica,
                settings.redis.max_connections,
                settings.redis.socket_connect_timeout_sec,
                settings.redis.socket_timeout_sec,
            )
        ),
        fixtures_ttl=timedelta(seconds=wrexham.cache_ttls.fixtures_ttl_sec),
        live_matches_ttl=timedelta(seconds=wrexham.cache_ttls.live_matches_ttl_sec),
        standings_ttl=timedelta(seconds=wrexham.cache_ttls.standings_ttl_sec),
    )
    return WrexhamIngester(
        backend=backend,
        store=store,
        season=wrexham.season,
        fixtures_interval=timedelta(seconds=wrexham.job.fixtures_refresh_interval_sec),
        standings_interval=timedelta(seconds=wrexham.job.standings_refresh_interval_sec),
    )


async def _run(interval_sec: float) -> None:  # pragma: no cover
    """Run the ingester until SIGTERM or SIGINT."""
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop_event.set)

    ingester = _build_ingester()
    try:
        await ingester.run_loop(interval_sec, stop_event)
    finally:
        await ingester.shutdown()
        logger.info("Wrexham ingester stopped")


cli = typer.Typer(name="wrexham", help="Ingest Wrexham widget data from SportsDataIO")


@cli.command("run-loop")
def run_loop(
    interval_sec: float = typer.Option(
        settings.widgets.providers.wrexham.job.loop_interval_sec,
        help="Seconds between runs.",
    ),
) -> None:  # pragma: no cover
    """Continuously ingest Wrexham data into Redis until stopped."""
    if not settings.providers.sports.sportsdata.api_key:
        logger.error(
            "Missing SportsDataIO API key: set MERINO_PROVIDERS__SPORTS__SPORTSDATA__API_KEY"
        )
        raise typer.Exit(code=1)

    asyncio.run(_run(interval_sec))
