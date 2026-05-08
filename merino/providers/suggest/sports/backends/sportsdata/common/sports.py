"""Individual Sport Definitions.

This contains the sport specific calls and data formats which are normalized.
"""

import asyncio
import logging
import orjson
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

# We use this for each Sport subclass, so that there's some flexibility for what config
# values are used and passed.
from dynaconf.base import LazySettings
from httpx import AsyncClient

from merino.cache.redis import RedisAdapter
from merino.cache.none import NoCacheAdapter
from merino.providers.suggest.sports import LOGGING_TAG
from merino.providers.suggest.sports.backends.sportsdata.common.error import SportsDataError
from merino.providers.suggest.sports.backends import get_data
from merino.providers.suggest.sports.backends.sportsdata.common import SportCategory
from merino.providers.suggest.sports.backends.sportsdata.common.data import (
    Sport,
    SportTerms,
    Team,
    Event,
)

FORCE_IMPORT = ""

# When creating a new sport class, add its entry to SPORT_CATEGORY_MAP below.
# The key must match the class name, as that is what is stored in the `Event.sport` field.
# There's ways to be more clever with this but due to the low number and velocity
# keeping it simple is best for now.
#
# The test test_sport_subclasses_have_category_mapping will catch any missing entries,
# as long as Sport subclasses remain defined in this file (will need to update
# the test logic if that changes)


SPORT_CATEGORY_MAP: dict[str, SportCategory] = {
    "NFL": SportCategory.Football,
    "NHL": SportCategory.Hockey,
    "NBA": SportCategory.Basketball,
    "UCL": SportCategory.Soccer,
    "MLB": SportCategory.Baseball,
    # "EPL": SportCategory.Soccer,
    "WCS": SportCategory.Soccer,
    "FIFA": SportCategory.Soccer,
}

# Global logger
logger = logging.getLogger(__name__)


class NFL(Sport):
    """National Football League"""

    season: str | None = None
    week: int | None = 0
    _lock: asyncio.Lock

    def __init__(self, settings: LazySettings, *args, **kwargs):
        name = self.__class__.__name__
        super().__init__(
            settings=settings,
            name=name,
            base_url=settings.sportsdata.get(
                f"base_url.{name.lower()}",
                default=f"https://api.sportsdata.io/v3/{name.lower()}/scores/json",
            ),
            season=None,
            week=0,
            cache_dir=settings.sportsdata.get("cache_dir"),
            team_ttl=timedelta(weeks=4),
            lock=asyncio.Lock(),
        )
        self._lock = asyncio.Lock()
        self.normalized_terms.update(
            {
                SportTerms.GAME_ID: "GlobalGameID",
                SportTerms.AWAY_TEAM_ID: "GlobalAwayTeamID",
                SportTerms.HOME_TEAM_ID: "GlobalHomeTeamID",
                SportTerms.HOME_TEAM_SCORE: "HomeScore",
                SportTerms.AWAY_TEAM_SCORE: "AwayScore",
                SportTerms.TEAM_ID: "GlobalTeamID",
            }
        )

    async def get_team(self, id: int) -> Team | None:
        """Attempt to find the team information in a thread-locking manner."""
        async with self._lock:
            team = self.teams.get(id)
        return team

    async def get_season(self, client: AsyncClient):
        """Get the current season"""
        # see: https://sportsdata.io/developers/api-documentation/nfl#timeframesepl
        if self.season is not None:
            return
        logger.debug(f"{LOGGING_TAG} Getting timeframe for {self.name} ")
        url = f"{self.base_url}/Timeframes/current"
        response = await get_data(
            client=client,
            url=url,
            ttl=timedelta(hours=4),
            cache_dir=self.cache_dir,
            args={"key": self.api_key},
        )
        """
        # Sample response:

        [{
            'SeasonType': 1,
            'Season': 2025,
            'Week': 3,
            'Name': 'Week 3',
            'ShortName': 'Week 3',
            'StartDate': '2025-09-17T00:00:00',
            'EndDate': '2025-09-23T23:59:59',
            'FirstGameStart': '2025-09-18T20:15:00',
            'FirstGameEnd': '2025-09-19T00:15:00',
            'LastGameEnd': '2025-09-23T00:15:00',
            'HasGames': True,
            'HasStarted': True,
            'HasEnded': False,
            'HasFirstGameStarted': True,
            'HasFirstGameEnded': True,
            'HasLastGameEnded': True,
            'ApiSeason': '2025REG',
            'ApiWeek': '3'
        }]
        """
        # Special case the Superbowl
        if not response[0].get("ApiSeason").endswith("STAR"):
            self.season = response[0].get("ApiSeason")
            self.week = response[0].get("ApiWeek")
        else:
            # The ProBowl interferes with displaying the Superbowl.
            self.season = response[0].get("ApiSeason").replace("STAR", "POST")
            self.week = 4
        if self.week is None:
            logger.debug(f"{LOGGING_TAG} No week, no events")
            return
        start = response[0].get("StartDate")
        end = response[0].get("EndDate")
        logger.debug(f"{LOGGING_TAG} {self.name} {self.season} week {self.week} {start} to {end}")

    async def update_teams(self, client: AsyncClient):
        """NFL requires a nightly "Timeframe" lookup."""
        await self.get_season(client=client)
        # Now get the team information:
        url = f"{self.base_url}/Teams"
        response = await get_data(
            client=client,
            url=url,
            ttl=timedelta(hours=4),
            cache_dir=self.cache_dir,
            args={"key": self.api_key},
        )
        async with self._lock:
            self.load_teams_from_source(response)

    async def update_events(self, client: AsyncClient):
        """Update the events for this sport in the elastic search database"""
        await self.get_season(client=client)
        logger.debug(f"{LOGGING_TAG} Getting Events for {self.name}")
        local_timezone = ZoneInfo("America/New_York")
        # get this week and next week
        if self.week is None:
            logger.debug(f"{LOGGING_TAG} No events (No week)")
            return
        for week in [int(self.week), int(self.week) + 1]:
            url = f"{self.base_url}/ScoresBasic/{self.season}/{week}"
            response = await get_data(
                client=client,
                url=url,
                ttl=timedelta(minutes=5),
                cache_dir=self.cache_dir,
                args={"key": self.api_key},
            )

            self.load_scores_from_source(
                response,
                event_timezone=local_timezone,
            )


class NHL(Sport):
    """National Hockey League"""

    season: str | None = None
    teams: dict[int, Any] = {}
    _lock: asyncio.Lock

    def __init__(self, settings: LazySettings, *args, **kwargs):
        name = self.__class__.__name__
        super().__init__(
            settings=settings,
            name=name,
            base_url=settings.sportsdata.get(
                f"base_url.{name.lower()}",
                default=f"https://api.sportsdata.io/v3/{name.lower()}/scores/json",
            ),
            season=None,
            cache_dir=settings.sportsdata.get("cache_dir"),
            event_ttl=timedelta(hours=48),
            team_ttl=timedelta(weeks=4),
        )
        self._lock = asyncio.Lock()
        self.normalized_terms = self.normalized_terms.copy()
        # GlobalTeam* not available for scores, use TeamID
        self.normalized_terms.update(
            {
                SportTerms.GAME_ID: "GameID",
                SportTerms.AWAY_TEAM_ID: "AwayTeamID",
                SportTerms.HOME_TEAM_ID: "HomeTeamID",
                SportTerms.TEAM_ID: "TeamID",
            }
        )

    async def get_team(self, id: int) -> Team | None:
        """Fetch team information using local locking"""
        async with self._lock:
            return self.teams.get(id)

    async def get_season(self, client: AsyncClient):
        """Get the current season"""
        if self.season is not None:
            return
        logger.debug(f"{LOGGING_TAG} Getting {self.name} season ")
        url = f"{self.base_url}/CurrentSeason"
        response = await get_data(
            client=client,
            url=url,
            ttl=timedelta(hours=4),
            cache_dir=self.cache_dir,
            args={"key": self.api_key},
        )
        """
        {
            "Season":2026,
            "StartYear":2025,
            "EndYear":2026,
            "Description":"2025-26",
            "RegularSeasonStartDate":"2025-10-07T00:00:00",
            "PostSeasonStartDate":"2026-04-18T00:00:00",
            "SeasonType":"PRE",
            "ApiSeason":"2026PRE"
        }
        """
        self.season = response.get("ApiSeason")

    async def update_teams(self, client: AsyncClient):
        """Fetch active team information"""
        await self.get_season(client=client)
        if self.season is None:
            logger.info(f"{LOGGING_TAG} Skipping out of season {self.name}")
            return
        logger.debug(f"{LOGGING_TAG} Getting {self.name} teams ")
        url = f"{self.base_url}/teams"
        response = await get_data(
            client=client,
            url=url,
            ttl=timedelta(hours=4),
            cache_dir=self.cache_dir,
            args={"key": self.api_key},
        )
        # NOTE:
        # Sportsdata lists the Superbowl teams as "AFC" vs "NFC".
        self.load_teams_from_source(response)

    async def update_events(self, client: AsyncClient):
        """Update schedules and game scores for this sport"""
        await self.get_season(client=client)
        logger.debug(f"{LOGGING_TAG} Getting {self.name} schedules")
        url = f"{self.base_url}/SchedulesBasic/{self.season}"
        local_timezone = ZoneInfo("America/New_York")
        response = await get_data(
            client=client,
            url=url,
            ttl=timedelta(minutes=5),
            cache_dir=self.cache_dir,
            args={"key": self.api_key},
        )
        self.load_schedules_from_source(response, event_timezone=local_timezone)
        date_list = []
        for _id, event in list(self.events.items()):
            # sportsdata.io keys date-by-day endpoints on the league's local game day,
            # not UTC. event.date is UTC, so a 10pm-ET game lives on the prior day's URL.
            day = event.date.astimezone(local_timezone).strftime("%Y-%b-%d").upper()
            if not event.status.is_scheduled() and day not in date_list:
                url = f"{self.base_url}/GamesByDate/{day}"
                response = await get_data(
                    client=client,
                    url=url,
                    ttl=timedelta(minutes=5),
                    cache_dir=self.cache_dir,
                    args={"key": self.api_key},
                )
                self.load_scores_from_source(response, event_timezone=local_timezone)
            date_list.append(day)


class NBA(Sport):
    """National Basketball Association"""

    season: str | None = None
    _lock: asyncio.Lock

    def __init__(self, settings: LazySettings, *args, **kwargs):
        name = self.__class__.__name__
        super().__init__(
            settings=settings,
            name=name,
            base_url=settings.sportsdata.get(
                f"base_url.{name.lower()}",
                default=f"https://api.sportsdata.io/v3/{name.lower()}/scores/json",
            ),
            cache_dir=settings.sportsdata.get("cache_dir"),
            team_ttl=timedelta(weeks=4),
        )
        self._lock = asyncio.Lock()
        self.normalized_terms.update(
            {
                SportTerms.GAME_ID: "GlobalGameID",
                SportTerms.AWAY_TEAM_ID: "GlobalAwayTeamID",
                SportTerms.HOME_TEAM_ID: "GlobalHomeTeamID",
                SportTerms.TEAM_ID: "GlobalTeamID",
            }
        )

    async def get_team(self, id: int) -> Team | None:
        """Fetch a team from the thread locked source"""
        async with self._lock:
            return self.teams.get(id)

    async def get_season(self, client: AsyncClient):
        """Get the current season"""
        if self.season:
            return
        logger.debug(f"{LOGGING_TAG} Getting {self.name} season ")
        url = f"{self.base_url}/CurrentSeason"
        response = await get_data(
            client=client,
            url=url,
            ttl=timedelta(hours=4),
            cache_dir=self.cache_dir,
            args={"key": self.api_key},
        )
        """
        {
            "Season":2026,
            "StartYear":2025,
            "EndYear":2026,
            "Description":"2025-26",
            "RegularSeasonStartDate":"2025-10-07T00:00:00",
            "PostSeasonStartDate":"2026-04-18T00:00:00",
            "SeasonType":"PRE",
            "ApiSeason":"2026PRE"
        }
        """
        self.season = response.get("ApiSeason")

    async def update_teams(self, client: AsyncClient):
        """Fetch active team information"""
        await self.get_season(client=client)
        logger.debug(f"{LOGGING_TAG} Getting {self.name} teams ")
        url = f"{self.base_url}/teams"
        response = await get_data(
            client=client,
            url=url,
            ttl=timedelta(hours=4),
            cache_dir=self.cache_dir,
            args={"key": self.api_key},
        )
        async with self._lock:
            self.load_teams_from_source(response)

    async def update_events(self, client: AsyncClient):
        """Update schedules and game scores for this sport"""
        await self.get_season(client=client)
        if self.season is None:
            logger.info(
                f"{LOGGING_TAG} Skipping out of season {self.name}"
            )  # pragma: no cover "informational"
        logger.debug(f"{LOGGING_TAG} Getting {self.name} schedules")
        local_timezone = ZoneInfo("America/New_York")
        url = f"{self.base_url}/SchedulesBasic/{self.season}"
        response = await get_data(
            client=client,
            url=url,
            ttl=timedelta(minutes=5),
            cache_dir=self.cache_dir,
            args={"key": self.api_key},
        )
        self.load_schedules_from_source(response, event_timezone=local_timezone)
        date_list = []
        # update scores based on events:
        # Events may cross multiple days, so we should update those scores.
        for _id, event in list(self.events.items()):
            # sportsdata.io keys date-by-day endpoints on the league's local game day,
            # not UTC. event.date is UTC, so a 10pm-ET game lives on the prior day's URL.
            day = event.date.astimezone(local_timezone).strftime("%Y-%b-%d").upper()
            if not event.status.is_scheduled() and day not in date_list:
                url = f"{self.base_url}/ScoresBasic/{day}"
                response = await get_data(
                    client=client,
                    url=url,
                    ttl=timedelta(minutes=5),
                    cache_dir=self.cache_dir,
                    args={"key": self.api_key},
                )
                self.load_scores_from_source(response, event_timezone=local_timezone)
                date_list.append(day)


class UCL(Sport):
    """Soccer: United Champions League"""

    season: str | None = None
    _lock: asyncio.Lock

    def __init__(self, settings: LazySettings, *args, **kwargs):
        name = self.__class__.__name__
        super().__init__(
            settings=settings,
            name=name,
            base_url=settings.sportsdata.get(
                f"base_url.{name.lower()}",
                default="https://api.sportsdata.io/v4/soccer/scores/json",
            ),
            cache_dir=settings.sportsdata.get("cache_dir"),
            team_ttl=timedelta(weeks=4),
        )
        self._lock = asyncio.Lock()
        self.normalized_terms.update(
            {
                SportTerms.GAME_ID: "GlobalGameId",
                SportTerms.AWAY_TEAM_ID: "GlobalAwayTeamId",
                SportTerms.AWAY_TEAM_KEY: "AwayTeamKey",
                SportTerms.HOME_TEAM_ID: "GlobalHomeTeamId",
                SportTerms.HOME_TEAM_KEY: "HomeTeamKey",
                SportTerms.TEAM_ID: "GlobalTeamId",
            }
        )

    async def get_season(self, client: AsyncClient):
        """Get the current season (which is just the current year)"""
        self.season = str(datetime.now(tz=timezone.utc).year)

    async def get_team(self, id: int) -> Team | None:
        """Fetch a team from the thread locked source"""
        async with self._lock:
            return self.teams.get(id)

    async def update_teams(self, client: AsyncClient):
        """Fetch active team information"""
        await self.get_season(client=client)
        logger.debug(f"{LOGGING_TAG} Getting {self.name} teams ")
        url = f"{self.base_url}/Teams/{self.name.lower()}"
        """
        [{
            "TeamId": 509,
            "AreaId": 68,
            "VenueId": 2,
            "Key": "ARS",
            "Name": "Arsenal FC",
            "FullName": "Arsenal Football Club ",
            "Active": true,
            "AreaName": "England",
            "VenueName": "Emirates Stadium",
            "Gender": "Male",
            "Type": "Club",
            "Address": null,
            "City": null,
            "Zip": null,
            "Phone": null,
            "Fax": null,
            "Website": "http://www.arsenal.com",
            "Email": null,
            "Founded": 1886,
            "ClubColor1": "Red",
            "ClubColor2": "White",
            "ClubColor3": null,
            "Nickname1": "The Gunners",
            "Nickname2": null,
            "Nickname3": null,
            "WikipediaLogoUrl": "https://upload.wikimedia.org/wikipedia/en/5/53/Arsenal_FC.svg",
            "WikipediaWordMarkUrl": null,
            "GlobalTeamId": 90000509
        },
        ...
        ]
        """
        response = await get_data(
            client=client,
            url=url,
            ttl=timedelta(hours=4),
            cache_dir=self.cache_dir,
            args={"key": self.api_key},
        )
        async with self._lock:
            self.load_teams_from_source(response)

    async def update_events(self, client: AsyncClient):
        """Update schedules and game scores for this sport"""
        await self.get_season(client=client)
        logger.debug(f"{LOGGING_TAG} Getting {self.name} schedules")
        url = f"{self.base_url}/SchedulesBasic/{self.name}/{self.season}"
        local_timezone = ZoneInfo("UTC")
        response = await get_data(
            client=client,
            url=url,
            ttl=timedelta(minutes=5),
            cache_dir=self.cache_dir,
            args={"key": self.api_key},
        )
        self.load_schedules_from_source(response, event_timezone=local_timezone)
        date_list = []
        # update scores based on events:
        # Events may cross multiple days, so we should update those scores.
        for _id, event in list(self.events.items()):
            day = event.date.strftime("%Y-%b-%d").upper()
            if not event.status.is_scheduled() and day not in date_list:
                url = f"{self.base_url}/ScoresBasic/{self.name}/{day}"
                response = await get_data(
                    client=client,
                    url=url,
                    ttl=timedelta(minutes=5),
                    cache_dir=self.cache_dir,
                    args={"key": self.api_key},
                )
                self.load_scores_from_source(response, event_timezone=local_timezone)
                date_list.append(day)


class MLB(Sport):
    """Major League Baseball"""

    season: str | None = None
    _lock: asyncio.Lock

    def __init__(self, settings: LazySettings, *args, **kwargs):
        name = self.__class__.__name__
        super().__init__(
            settings=settings,
            name=name,
            base_url=settings.sportsdata.get(
                f"base_url.{name.lower()}",
                default=f"https://api.sportsdata.io/v3/{name.lower()}/scores/json",
            ),
            season=None,
            cache_dir=settings.sportsdata.get("cache_dir"),
            event_ttl=timedelta(hours=48),
            team_ttl=timedelta(weeks=4),
        )
        self._lock = asyncio.Lock()
        # GlobalTeamID not in schedule
        self.normalized_terms.update(
            {
                SportTerms.GAME_ID: "GameID",
                SportTerms.AWAY_TEAM_SCORE: "AwayTeamRuns",
                SportTerms.HOME_TEAM_SCORE: "HomeTeamRuns",
                SportTerms.TEAM_ID: "TeamID",
            }
        )

    async def get_season(self, client: AsyncClient):
        """Get the current season"""
        if self.season is not None:
            return  # pragma: no cover
        logger.debug(f"{LOGGING_TAG} Getting {self.name} season")
        url = f"{self.base_url}/CurrentSeason"
        response = await get_data(
            client=client,
            url=url,
            ttl=timedelta(hours=4),
            cache_dir=self.cache_dir,
            args={"key": self.api_key},
        )
        """
        {
            "Season":2026,
            "RegularSeasonStartDate":"2025-10-07T00:00:00",
            "PostSeasonStartDate":"2026-04-18T00:00:00",
            "SeasonType":"PRE",
            "ApiSeason":"2026PRE"
        }
        """
        self.season = response.get("ApiSeason")

    async def update_teams(self, client: AsyncClient):
        """Fetch active team information"""
        await self.get_season(client=client)
        if self.season is None:  # pragma: no cover
            logger.info(f"{LOGGING_TAG} Skipping out of season {self.name}")
            return
        logger.debug(f"{LOGGING_TAG} Getting {self.name} teams ")
        url = f"{self.base_url}/teams"
        response = await get_data(
            client=client,
            url=url,
            ttl=timedelta(hours=4),
            cache_dir=self.cache_dir,
            args={"key": self.api_key},
        )
        async with self._lock:
            self.load_teams_from_source(response)

    async def get_team(self, id: int) -> Team | None:
        """Attempt to find the team information in a thread-locking manner."""
        async with self._lock:
            team = self.teams.get(id)
        return team

    async def update_events(self, client: AsyncClient):
        """Fetch the list of events for the sport. (5 min interval)"""
        local_timezone = ZoneInfo("America/New_York")
        logger.debug(f"{LOGGING_TAG} Getting {self.name} schedules")
        url = f"{self.base_url}/SchedulesBasic/{self.season}"
        response = await get_data(
            client=client,
            url=url,
            ttl=timedelta(minutes=5),
            cache_dir=self.cache_dir,
            args={"key": self.api_key},
        )
        self.load_schedules_from_source(response, event_timezone=local_timezone)
        date_list = []
        # update scores based on events
        # Events may cross multiple days, so we should update those scores.
        for _id, event in list(self.events.items()):
            # sportsdata.io keys date-by-day endpoints on the league's local game day,
            # not UTC. event.date is UTC, so a 10pm-ET game lives on the prior day's URL.
            day = event.date.astimezone(local_timezone).strftime("%Y-%b-%d").upper()
            if not event.status.is_scheduled() and day not in date_list:
                url = f"{self.base_url}/ScoresBasic/{day}"
                response = await get_data(
                    client=client,
                    url=url,
                    ttl=timedelta(minutes=5),
                    cache_dir=self.cache_dir,
                    args={"key": self.api_key},
                )
                self.load_scores_from_source(response, event_timezone=local_timezone)
                date_list.append(day)


class WCS(Sport):
    """Soccer: World Cup support"""

    ## Right, this class is the general handler for all things World Cup. Ideally, all the other
    ## jobs, interfaces, and what-not call into this class in order to get things running, fetch
    ## and process data, or return results.

    season: str | None = None
    fake_name: str = "World Cup"
    cache_prefix: str = "sport:wcs:v1"  # Unique prefix for Redis
    _lock: asyncio.Lock
    teams: dict[int, Team] = {}
    refreshed: datetime = datetime.now(tz=timezone.utc)

    def __init__(
        self,
        settings: LazySettings,
        *args,
        cache: RedisAdapter | NoCacheAdapter = NoCacheAdapter(),
        **kwargs,
    ):
        # name = self.__class__.__name__
        name = "fifa"
        # sport specific settings TODO: copy this to other sports.
        sport_settings = settings.sportsdata.get(self.__class__.__name__, {})
        super().__init__(
            settings=settings,
            name=name,
            base_url=sport_settings.get(
                "base_url", "https://api.sportsdata.io/v4/soccer/scores/json"
            ),
            cache_dir=settings.sportsdata.get("cache_dir"),
            team_ttl=timedelta(weeks=sport_settings.get("team_ttl_weeks", 12)),
            event_ttl=timedelta(weeks=sport_settings.get("event_ttl_weeks.wcs", 12)),
        )
        self._lock = asyncio.Lock()
        self.cache = cache
        self.normalized_terms.update(
            {
                SportTerms.GAME_ID: "GlobalGameId",
                SportTerms.AWAY_TEAM_ID: "GlobalAwayTeamId",
                SportTerms.AWAY_TEAM_KEY: "AwayTeamKey",
                SportTerms.HOME_TEAM_ID: "GlobalHomeTeamId",
                SportTerms.HOME_TEAM_KEY: "HomeTeamKey",
                SportTerms.TEAM_ID: "GlobalTeamId",
                SportTerms.COLOR1: "ClubColor1",
                SportTerms.COLOR2: "ClubColor2",
                SportTerms.COLOR3: "ClubColor3",
                SportTerms.COLOR4: "ClubColor4",
            }
        )

    # Note: this is covered by `test_wcs_init_cache` but I believe that the heavy use of Mocks
    # prevents coverage from detecting that the lines are accessed. Adding "no cover" to get
    # coverage numbers under control. (it's temporary anyway, we're dropping it with the WCS widget.)
    async def init_cache(  # pragma: no cover "widget"
        self, client: AsyncClient, force: bool = False
    ):  # pragma: no cover "widget/mocks"
        """Initialize the Redis cache, if needed

        There are some bits of data that are long lived. In our case, each team
        and event has a `RegionId` that maps to the Areas returned by `../Areas` endpoint.
        The Area result contains a LOT of information, but we really only care about
        the country code, because that's how we will identify a given team.

        There's a STRONG temptation to use the `team.key` since that also appears to map
        to the country code, but SportsData may not be consistent about that (see the
        fact that they used the same key code for two different countries).

        """
        meta_key = f"{self.cache_prefix}:meta"
        last_update = int.from_bytes(
            await self.cache.get(f"{meta_key}:updated") or int(0).to_bytes()
        )

        # Has it been over a year since we last updated the meta info?
        lock_period = 365
        if not force and last_update:  # pragma: no cache "widget"
            if last_update > int(
                (datetime.now(tz=timezone.utc) - timedelta(days=lock_period)).timestamp()
            ):
                return
        now = datetime.now(tz=timezone.utc)
        mylock = int((now + timedelta(seconds=30)).timestamp())
        # if we can get the lock, initialize the data.
        if await self.cache.setnx(
            f"{meta_key}:lock", value=mylock.to_bytes(8), nx=True, ttl=timedelta(seconds=30)
        ):
            try:
                logging.info(f"{LOGGING_TAG} Initializing Cache")
                # We got the lock, we can initialize things.
                # to initial stuff.
                await self.load_areas(client)
                await self.update_teams(client)
                await self.cache_teams()
                complete = int(datetime.now(tz=timezone.utc).timestamp())
                logging.info(f"{LOGGING_TAG} Marking db initialized as of {complete}")
                # We're done, carry on...
                await self.cache.set(f"{meta_key}:updated", complete.to_bytes(8))
            finally:
                await self.cache.delete(f"{meta_key}:lock")

    async def load_areas(self, client) -> None:
        """Fetch and load the countries to the cache"""
        # Fetch the area info, specifically the country code.
        # Each event and team has an `AreaId` which we will use to map
        # to the individual country. This should not change, so we only need
        # to update once, and maybe once per year.
        url = f"{self.base_url}/Areas"
        response = await get_data(
            client=client,
            url=url,
            ttl=timedelta(weeks=25),
            cache_dir=self.cache_dir,
            args={"key": self.api_key},
        )
        # Sample Response:
        """
        [
            {
                "AreaId": 1,
                "CountryCode": "INT",
                "Name": "World",
                "Competitions": [...]
            },
            {
                "AreaId": 2,
                "CountryCode": "ASI",
                "Name": "Asia",
                "Competitions": [...]
            }
        ]
        """
        logging.info(f"{LOGGING_TAG} Pre Loading Countries")
        for area in response:
            # build the reverse index to get the country code and id.
            country_data = {
                "name": area["Name"],
                "code": area["CountryCode"],
            }
            # cache this for later, we're gonna need them for teams.
            await self.cache.hset(f"{self.cache_prefix}:area:{area['AreaId']}", country_data)

    async def get_season(self, client: AsyncClient) -> None:
        """Get the current season (which is just the current year)"""
        self.season = str(datetime.now(tz=timezone.utc).year)

    async def get_country(self, area_id: int | None) -> dict[bytes, bytes] | None:
        """Return cached country info for this ID"""
        if not area_id:
            return None
        return await self.cache.hgetall(f"{self.cache_prefix}:area:{area_id}")

    async def get_team(self, id: int) -> Team | None:
        """Fetch a team from the thread locked source"""
        # This may become a high traffic function, so we should try to use
        # a cached value if at all possible.
        # Normally, this is only used by the ingestion job, which pre-loads
        # the teams whenever it's updating events and scores. For the widget,
        # though, this may be needed more often.
        async with self._lock:
            # import pdb;pdb.set_trace()
            """
            team_data = await self.cache.get(f"{self.cache_prefix}:team:{id}")
            if False:  # team_data:
                TODO: recreate the Team using the cached data.
                data = json.loads(team_data)
                TODO: Fill this out.
                team = Team(  # type: ignore
                    id=data.get("id"),
                    fullname=data.get("name"),
                    key=data.get("key"),
                    locale=data.get("country"),
                    aliases="",
                    colors=data.get("colors"),
                )
                team.id = data.get("id")
                return team
            """
            return self.teams.get(id)

    async def async_load_teams_from_source(self, data: list[dict[str, Any]]) -> dict[int, Team]:
        """Create the Team entries from the data source

        This presumes that we are receiving data that complies with the SportsData.io
        `Team` data dictionary (See https://sportsdata.io/developers/data-dictionary/nfl#team)

        If we ever have a different data provider, this will need to be moved to the
        SportData provider class.
        """
        # this is a specialized version of the normal `load_teams_from_source`.
        # This should try to
        for team_data in data:
            try:
                area = await self.get_country(team_data.get("AreaId"))
                # TODO: get `eliminated` field from ??
                team = Team.from_data(
                    team_data=team_data,
                    term_filter=self.term_filter,
                    team_ttl=self.team_ttl,
                    normalized_terms=self.normalized_terms,
                )
                if area:
                    team.country = area.get(b"code", b"UNK").decode()  # pragma: no cover "widget"
                self.teams[team.id] = team
            except SportsDataError:
                pass  # pragma: no cover "skip error"
        self.refreshed = datetime.now(tz=timezone.utc)
        await self.cache_teams()
        return self.teams

    async def update_teams(self, client: AsyncClient):
        """Fetch active team information"""
        await self.get_season(client=client)
        logger.debug(f"{LOGGING_TAG} Getting {self.name} teams ")
        url = f"{self.base_url}/Teams/{self.name.lower()}"

        response = await get_data(
            client=client,
            url=url,
            ttl=timedelta(hours=4),
            cache_dir=self.cache_dir,
            args={"key": self.api_key},
        )
        async with self._lock:
            await self.async_load_teams_from_source(response)

    def team_as_serialized(self, team: Team) -> bytes:  # pragma: no cover "widget"
        """Serialize a team as a dictionary for the widget"""
        # TODO: Populate the eliminated field (from old team info?)
        serialized = team.model_dump()
        serialized["expiry"] = team.expiry.timestamp()
        serialized["updated"] = team.updated.timestamp()
        return orjson.dumps(serialized)

    def event_as_serialized(self, event: Event) -> bytes:  # pragma: no cover "widget"
        """Serialize an event as a dictionary for the widget"""
        # import pdb;pdb.set_trace()
        # TODO: add more team info?
        serialized = event.model_dump()
        serialized["sport"] = self.fake_name
        # munge the dates.
        serialized["date"] = event.date.timestamp()
        serialized["expiry"] = event.expiry.timestamp()
        serialized["updated"] = event.updated.timestamp() if event.updated else None
        return orjson.dumps(serialized)

    async def cache_teams(self) -> None:  # pragma: no cover "widget"
        """Write the team data to the redis cache for the widget"""
        # Widget: Store teams to Redis
        ids = []
        for teamId, team in self.teams.items():
            id = f"{self.cache_prefix}:team:{teamId}"
            await self.cache.set(id, self.team_as_serialized(team))
            ids.append(id)
        # for now, dump the list of team ids into a meta list so that we can save doing a scan later.
        # TODO: replace with vadd when available.
        refresh_key = f"{self.cache_prefix}:meta:team_refresh"
        last_update = await self.cache.get(refresh_key)
        # add a lock check, otherwise everyone is going to try to update this at startup.
        # We'll arbitrarily update this every 12 hours or so.
        # TODO: Team cache TTL should probably be a setting
        if not last_update or (
            last_update
            and datetime.fromtimestamp(int.from_bytes(last_update))
            < datetime.now(tz=timezone.utc) - timedelta(hours=12)
        ):
            now = datetime.now(tz=timezone.utc)
            ttl = timedelta(seconds=10)
            mylock = int((now + ttl).timestamp())
            if await self.cache.setnx(
                f"{self.cache_prefix}:meta:team_lock", value=mylock.to_bytes(8), nx=True, ttl=ttl
            ):
                await self.cache.set(f"{self.cache_prefix}:meta:team_ids", orjson.dumps(ids))
                await self.cache.set(refresh_key, int(now.timestamp()).to_bytes(8))
                await self.cache.delete(f"{self.cache_prefix}:meta:team_lock")

    async def get_all_teams(self, client: AsyncClient) -> dict[int, Any]:
        """Return all the cached teams.

        For the `/teams` endpoint, return the `.values()` of the result.
        """
        # If we don't have any team info, or the local cache is stale
        if not self.teams or self.refreshed < datetime.now(tz=timezone.utc).replace(
            hour=0, minute=0, second=0
        ):
            # Try getting from the redis cache (in case some other app already fetched the info)
            team_ids = await self.cache.get(f"{self.cache_prefix}:meta:team_ids")
            # We haven't fetched the data yet, so let's see if we can do it.
            if not team_ids:
                await self.update_teams(client)
                return self.teams
            # Ok, we have redis cached data, let's construct our local cache.
            if team_ids:
                team_ids = orjson.loads(team_ids)
                str_teams = await self.cache.mget(team_ids)
                if str_teams:
                    for bteam in str_teams:
                        team = Team(**orjson.loads(bteam))
                        self.teams[int(team.id)] = team
                self.refreshed = datetime.now(tz=timezone.utc)
        return self.teams

    async def update_events(self, client: AsyncClient, allow_no_teams: bool = False):
        """Update schedules and game scores for this sport"""
        await self.get_season(client=client)
        logger.debug(f"{LOGGING_TAG} Getting {self.name} schedules")
        url = f"{self.base_url}/SchedulesBasic/{self.name}/{self.season}"
        local_timezone = ZoneInfo("UTC")
        response = await get_data(
            client=client,
            url=url,
            ttl=timedelta(minutes=5),
            cache_dir=self.cache_dir,
            args={"key": self.api_key},
        )
        self.load_schedules_from_source(response, event_timezone=local_timezone)
        date_list = []
        # update scores based on events:
        # Events may cross multiple days, so we should update those scores.
        for _id, event in list(self.events.items()):
            day = event.date.strftime("%Y-%b-%d").upper()
            if not event.status.is_scheduled() and day not in date_list:
                url = f"{self.base_url}/GamesByDate/{self.name}/{day}"
                response = await get_data(
                    client=client,
                    url=url,
                    ttl=timedelta(minutes=5),
                    cache_dir=self.cache_dir,
                    args={"key": self.api_key},
                )
                self.load_scores_from_source(
                    response,
                    event_timezone=local_timezone,
                )
                date_list.append(day)

        # Widget: Store events to Redis
        # Go through one more time to catch any stray events.
        # TODO: Put these in their own function?
        for event_id, event in list(self.events.items()):
            # import pdb; pdb.set_trace()
            serialized = self.event_as_serialized(event)
            await self.cache.set(f"{self.cache_prefix}:event:{event_id}", serialized)
            # Add the event to the zorder for date lookups
            await self.cache.zadd(
                f"{self.cache_prefix}:calendar",
                {f"{self.cache_prefix}:event:{event_id}": int(event.date.timestamp())},
                gt=True,
            )

    async def get_events_by_team(  # pragma: no cover "widget"
        self, team_key: str, start: datetime | None = None, end: datetime | None = None
    ) -> list[Event]:
        """Scan the cache looking for data that matches"""
        # This will need to fetch all events for a given team
        # TODO: we might be able to store this as a unique key "...:team_games:{team_key}": [global_event_id,...]
        # but that feels gross.
        raise NotImplementedError

    async def get_events_by_date(
        self, start: datetime | None = None, end: datetime | None = None
    ):  # pragma: no cover "widget"
        """Get events by start,end"""
        # TODO: build
        # scan the ssort list for events that fall between the start (min) and end (max)
        # fetch those event info.
        raise NotImplementedError


# THE FOLLOWING CLASSES ARE WIP:::


# class EPL(Sport):
#    """English Premier League"""
#
#    term_filter: list[str] = ["a", "club", "the", "football", "fc"]
#
#    def __init__(self, settings: LazySettings, *args, **kwargs):
#        name = self.__class__.__name__
#
#        super().__init__(
#            settings=settings,
#            name=name,
#            base_url=settings.sportsdata.get(
#                f"base_url.{name.lower()}",
#                default="https://api.sportsdata.io/v3/soccer/scores/json/",
#            ),
#            season=None,
#            week=None,
#            teams={},
#            lock=asyncio.Lock(),
#            *args,
#            **kwargs,
#        )
#
#    async def update(self, store: SportsDataStore):
#        """Fetch and update the Team Standing information."""
#        # TODO: Fill in update
#        # fetch the Standings data: (5 min interval)
#        """
#
#        """
#        standings_url = f"{self.base_url}/Standings/{self.name.lower()}"
#        response = await self.client.get(standings_url)
#        response.raise_for_status()
#        raw_data = response.json()
#        for round in raw_data:
#            pass
#        return
#
