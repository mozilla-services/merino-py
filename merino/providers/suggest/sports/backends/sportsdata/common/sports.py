"""Individual Sport Definitions.

This contains the sport specific calls and data formats which are normalized.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from time import time
from typing import Any
from zoneinfo import ZoneInfo

# We use this for each Sport subclass, so that there's some flexibility for what config
# values are used and passed.
from dynaconf.base import LazySettings
from httpx import AsyncClient

from merino.providers.suggest.sports import LOGGING_TAG
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
            day = event.date.strftime("%Y-%b-%d").upper()
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
            logger.info(f"{LOGGING_TAG} Skipping out of season {self.name}")
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
            day = event.date.strftime("%Y-%b-%d").upper()
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
            return
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

    season: str | None = None
    cache_prefix: str = "sport:wcs"
    _lock: asyncio.Lock

    def __init__(self, settings: LazySettings, *args, **kwargs):
        # name = self.__class__.__name__
        name = "FIFA"
        super().__init__(
            settings=settings,
            name=name,
            base_url=settings.sportsdata.get(
                "base_url.wcs",
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
                SportTerms.COLOR1: "ClubColor1",
                SportTerms.COLOR2: "ClubColor2",
                SportTerms.COLOR3: "ClubColor3",
                SportTerms.COLOR4: "ClubColor4",
            }
        )

    async def init_cache(self, client: AsyncClient):
        """Initialize the cache, if needed"""
        meta_key = self.cache.hgetall(f"{self.cache_prefix}:meta")
        # Has it been over a year since we last updated the meta info?
        updated = await self.cache.hget(meta_key, "meta_updated")
        if updated and updated < (datetime.now() - timedelta.days(365)):
            return
        # sigh, `hexpire` is not yet implemented (7.4.0), so manually check and clear any locks
        mylock = int(time())
        meta_key = f"{self.cache_prefix}:meta"
        prev = await self.cache.hget(meta_key, "lock")
        if prev is not None and prev < mylock:
            await self.cache.hdel(meta_key, "lock")
        if self.cache.hsetnx(meta_key, "lock", mylock) == 1:
            logging.info(f"{LOGGING_TAG} Initializing Cache")
            # We got the lock, we can initialize things.
            # await self.load_venues(client)
            complete = int(time())
            logging.info(f"{LOGGING_TAG} Marking db initialized as of {complete}")
            # We're done, carry on...
            await self.cache.hsetnx(meta_key, "meta_updated", complete)
            await self.cache.hdel(meta_key, "lock")

    async def load_venues(self, client):
        """Fetch and load the countries to the cache"""
        url = f"{self.base_url}/Areas?key={self.api_key}"
        response = await get_data(
            client=client,
            url=url,
            ttl=timedelta(weeks=25),
            cache_dir=self.cache_dir,
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
        countries = {}
        logging.info(f"{LOGGING_TAG} Pre Loading Countries and Venues")
        for area in response:
            # build the reverse index to get the country code and id.
            countries[area["Name"]] = {
                "id": area["AreaId"],
                "code": area["CountryCode"],
            }
        # Now that we have the long form of the countries, we can get the venues.
        url = f"{self.base_url}/Venues?key={self.api_key}"
        response = await get_data(
            client=client,
            url=url,
            ttl=timedelta(weeks=25),
            cache_dir=self.cache_dir,
        )
        # Sample Response
        """
        [
        {
            "VenueId": 1,
            "Name": "Vitality Stadium",
            "Address": "Dean Court",
            "City": "Bournemouth",
            "Zip": "BH7 7AF",
            "Country": "England",
            "Open": true,
            "Opened": 2001,
            "Nickname1": null,
            "Nickname2": null,
            "Capacity": 12000,
            "Surface": "Grass",
            "GeoLat": 50.73524,
            "GeoLong": -1.838309
        },
        {
            "VenueId": 2,
            "Name": "Emirates Stadium",
            "Address": "Queensland Road",
            "City": "Islington, Borough of London",
            "Zip": "N7 7AJ",
            "Country": "England",
            "Open": true,
            "Opened": 2006,
            "Nickname1": "Arsenal Stadium",
            "Nickname2": "Ashburton Grove",
            "Capacity": 60355,
            "Surface": "Grass",
            "GeoLat": 51.555074,
            "GeoLong": -0.108457
        }
        ]

        """
        for venue in response:
            if venue.get("Open") is True:
                continue
            record = {
                "id": venue["VenueId"],
                "name": venue["Name"],
                "city": venue["City"],
                "country": countries.get(venue["Country"]),
                "geo": [venue["GeoLat"], venue["GeoLong"]],
            }
            # Stuff this into a transaction?
            await self.cache.hmset(f"{self.cache_prefix}:venue:{venue['VenueId']}", record)

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

        response = await get_data(
            client=client,
            url=url,
            ttl=timedelta(hours=4),
            cache_dir=self.cache_dir,
            args={"key": self.api_key},
        )
        async with self._lock:
            self.load_teams_from_source(response)

        # Widget: Store teams to Redis
        for teamId, team in self.teams.items():
            await self.cache.hmset(f"{self.cache_prefix}:team:{teamId}", team)
        return self

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
            self.cache.hmset(f"{self.cache_prefix}:event:{event_id}", event)
            # Add the event to the zorder for date lookups
            self.cache.zadd(
                f"{self.cache_prefix}:calendar",
                {f"{self.cache_prefix}:event:{event_id}", int(event.date.timestamp())},
                gt=True,
            )
        return self

    async def get_events_by_team(
        self, team_key: str, start: datetime | None = None, end: datetime | None = None
    ) -> list[Event]:
        """Scan the cache looking for data that matches"""
        event_ids = await self.cache.scan(f"{self.cache_prefix}:{team_key}:*") or []
        if datetime:
            # filter by date-time:
            start = start or datetime.min
            end = end or datetime.max
            event_ids = filter(event_ids, lambda event: start <= event.date <= end)
        if not event_ids:
            return []
        events = []
        for id in event_ids:
            event = self.cache.get(id)
            # TODO: Check for expiry?
            if event:
                events.append(event)
        return events

    async def get_events_by_date(self, start: datetime | None = None, end: datetime | None = None):
        """Get events by start,end"""
        # TODO: build
        pass


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
