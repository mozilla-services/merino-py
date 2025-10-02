"""Individual Sport Definitions.

This contains the sport specific calls and data formats which are normalized.
"""

import asyncio
import logging
from datetime import timedelta

from dynaconf.base import LazySettings
from httpx import AsyncClient

from merino.providers.suggest.sports import LOGGING_TAG
from merino.providers.suggest.sports.backends import get_data
from merino.providers.suggest.sports.backends.sportsdata.common.data import (
    Sport,
    Team,
)

FORCE_IMPORT = ""


class NFL(Sport):
    """National Football League"""

    season: str | None
    week: int = 0
    _lock: asyncio.Lock

    def __init__(self, settings: LazySettings, *args, **kwargs):
        # for mypy
        name = self.__class__.__name__
        super().__init__(
            settings=settings,
            name=name,
            base_url=settings.providers.sports.sportsdata.get(
                f"base_url.{name.lower()}",
                default=f"https://api.sportsdata.io/v3/{name.lower()}/scores/json",
            ),
            season=None,
            week=0,
            cache_dir=settings.providers.sports.sportsdata.get("cache_dir"),
            team_ttl=timedelta(weeks=4),
            lock=asyncio.Lock(),
            **kwargs,
        )
        self._lock = asyncio.Lock()

    async def get_team(self, name: str) -> Team | None:
        """Attempt to find the team information in a thread-locking manner."""
        async with self._lock:
            team = self.teams.get(self.gen_key(name))
        return team

    async def update_teams(self, client: AsyncClient):
        """NFL requires a nightly "Timeframe" lookup."""
        # see: https://sportsdata.io/developers/api-documentation/nfl#timeframesepl
        logging.debug(f"{LOGGING_TAG} Getting timeframe for {self.name} ")
        url = f"{self.base_url}/Timeframes/current?key={self.api_key}"
        response = await get_data(
            client=client,
            url=url,
            ttl=timedelta(hours=4),
            cache_dir=self.cache_dir,
        )
        # [{
        #     'SeasonType': 1,
        #     'Season': 2025,
        #     'Week': 3,
        #     'Name': 'Week 3',
        #     'ShortName': 'Week 3',
        #     'StartDate': '2025-09-17T00:00:00',
        #     'EndDate': '2025-09-23T23:59:59',
        #     'FirstGameStart': '2025-09-18T20:15:00',
        #     'FirstGameEnd': '2025-09-19T00:15:00',
        #     'LastGameEnd': '2025-09-23T00:15:00',
        #     'HasGames': True,
        #     'HasStarted': True,
        #     'HasEnded': False,
        #     'HasFirstGameStarted': True,
        #     'HasFirstGameEnded': True,
        #     'HasLastGameEnded': True,
        #     'ApiSeason': '2025REG',
        #     'ApiWeek': '3'
        # }]
        # TODO: Store this info in meta
        self.season = response[0].get("ApiSeason")
        self.week = response[0].get("ApiWeek")
        start = response[0].get("StartDate")
        end = response[0].get("EndDate")
        logging.debug(f"{LOGGING_TAG} {self.name} week {self.week} {start} to {end}")
        # Now get the team information:
        url = f"{self.base_url}/Teams?key={self.api_key}"
        response = await get_data(
            client=client,
            url=url,
            ttl=timedelta(hours=4),
            cache_dir=self.cache_dir,
        )
        async with self._lock:
            self.load_teams_from_source(response)
        return self

    async def update_events(self, client: AsyncClient):
        """Update the events for this sport in the elastic search database"""
        logging.debug(f"{LOGGING_TAG} Getting Events for {self.name}")
        # get this week and next week
        for week in [int(self.week), int(self.week) + 1]:
            url = f"{self.base_url}/ScoresBasic/{self.season}/{week}?key={self.api_key}"
            response = await get_data(
                client=client,
                url=url,
                ttl=timedelta(minutes=5),
                cache_dir=self.cache_dir,
            )
            self.load_scores_from_source(response)
        return self


class NHL(Sport):
    """National Hockey League"""

    season: str | None
    _lock: asyncio.Lock

    def __init__(self, settings: LazySettings, *args, **kwargs):
        name = self.__class__.__name__
        super().__init__(
            settings=settings,
            name=name,
            base_url=settings.providers.sports.sportsdata.get(
                f"base_url.{name.lower()}",
                default=f"https://api.sportsdata.io/v3/{name.lower()}/scores/json",
            ),
            season=None,
            cache_dir=settings.providers.sports.sportsdata.get("cache_dir"),
            event_ttl=timedelta(hours=48),
            team_ttl=timedelta(weeks=4),
            **kwargs,
        )
        self._lock = asyncio.Lock()

    async def get_team(self, name: str) -> Team | None:
        """Fetch team information using local locking"""
        async with self._lock:
            return self.teams.get(self.gen_key(name))

    async def update_teams(self, client: AsyncClient):
        """Fetch active team information"""
        logging.debug(f"{LOGGING_TAG} Getting {self.name} season ")
        url = f"{self.base_url}/CurrentSeason?key={self.api_key}"
        response = await get_data(
            client=client,
            url=url,
            ttl=timedelta(hours=4),
            cache_dir=self.cache_dir,
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
        if self.season is None:
            logging.info(f"{LOGGING_TAG} Skipping out of season {self.name}")
            return self
        logging.debug(f"{LOGGING_TAG} Getting {self.name} teams ")
        url = f"{self.base_url}/teams?key={self.api_key}"
        response = await get_data(
            client=client,
            url=url,
            ttl=timedelta(hours=4),
            cache_dir=self.cache_dir,
        )
        self.load_teams_from_source(response)
        return self

    async def update_events(self, client: AsyncClient):
        """Update schedules and game scores for this sport"""
        logging.debug(f"{LOGGING_TAG} Getting {self.name} schedules")
        url = f"{self.base_url}/SchedulesBasic/{self.season}?key={self.api_key}"
        response = await get_data(
            client=client,
            url=url,
            ttl=timedelta(minutes=5),
            cache_dir=self.cache_dir,
        )
        self.load_schedules_from_source(response)
        return self


class NBA(Sport):
    """Major Hockey League"""

    season: str | None
    _lock: asyncio.Lock

    def __init__(self, settings: LazySettings, *args, **kwargs):
        name = self.__class__.__name__
        super().__init__(
            settings=settings,
            name=name,
            base_url=settings.providers.sports.sportsdata.get(
                f"base_url.{name.lower()}",
                default=f"https://api.sportsdata.io/v3/{name.lower()}/scores/json",
            ),
            season=None,
            cache_dir=settings.providers.sports.sportsdata.get("cache_dir"),
            team_ttl=timedelta(weeks=4),
            **kwargs,
        )
        self._lock = asyncio.Lock()

    async def get_team(self, name: str) -> Team | None:
        """Fetch a team from the thread locked source"""
        async with self._lock:
            return self.teams.get(self.gen_key(name))

    async def update_teams(self, client: AsyncClient):
        """Fetch active team information"""
        logging.debug(f"{LOGGING_TAG} Getting {self.name} season ")
        url = f"{self.base_url}/CurrentSeason?key={self.api_key}"
        response = await get_data(
            client=client,
            url=url,
            ttl=timedelta(hours=4),
            cache_dir=self.cache_dir,
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
        if self.season is None:
            logging.info(f"{LOGGING_TAG} Skipping out of season {self.name}")
            return self
        logging.debug(f"{LOGGING_TAG} Getting {self.name} teams ")
        url = f"{self.base_url}/teams?key={self.api_key}"
        response = await get_data(
            client=client,
            url=url,
            ttl=timedelta(hours=4),
            cache_dir=self.cache_dir,
        )
        async with self._lock:
            self.load_teams_from_source(response)
        return self

    async def update_events(self, client: AsyncClient):
        """Update schedules and game scores for this sport"""
        """Update the schedules for games"""
        logging.debug(f"{LOGGING_TAG} Getting {self.name} schedules")
        url = f"{self.base_url}/SchedulesBasic/{self.season}?key={self.api_key}"
        response = await get_data(
            client=client,
            url=url,
            ttl=timedelta(minutes=5),
            cache_dir=self.cache_dir,
        )
        self.load_schedules_from_source(response)
        return self


# THE FOLLOWING CLASSES ARE WIP:::


# class MLB(Sport):
#    """Major League Baseball"""
#
#    def __init__(self, settings: LazySettings, *args, **kwargs):
#        name = self.__class__.__name__
#
#        super().__init__(
#            name=name,
#            base_url=settings.providers.sports.sportsdata.get(
#                f"base_url.{name.lower()}",
#                default=f"https://api.sportsdata.io/v3/{name.lower()}/scores/json",
#            ),
#            season=None,
#            week=None,
#            teams={},
#            *args,
#            **kwargs,
#        )
#        self._lock = asyncio.Lock()
#
#    async def update_events(self, client: AsyncClient) -> list[Event]:
#        """Fetch the list of events for the sport. (5 min interval)"""
#        # https://api.sportsdata.io/v3/mlb/scores/json/teams?key=
#        # Sample:
#        """
#        [
#            {
#                "AwayTeamRuns": 0,
#                "HomeTeamRuns": 0,
#                "AwayTeamHits": 2,
#                "HomeTeamHits": 5,
#                "AwayTeamErrors": 0,
#                "HomeTeamErrors": 0,
#                "Attendance": null,
#                "GlobalGameID": 10076415,
#                "GlobalAwayTeamID": 10000012,
#                "GlobalHomeTeamID": 10000032,
#                "NeutralVenue": false,
#                "Inning": 4,
#                "InningHalf": "B",
#                "GameID": 76415,
#                "Season": 2025,
#                "SeasonType": 1,
#                "Status": "InProgress",
#                "Day": "2025-09-04T00:00:00",
#                "DateTime": "2025-09-04T16:10:00",
#                "AwayTeam": "PHI",
#                "HomeTeam": "MIL",
#                "AwayTeamID": 12,
#                "HomeTeamID": 32,
#                "RescheduledGameID": null,
#                "StadiumID": 92,
#                "IsClosed": false,
#                "Updated": "2025-09-04T17:19:20",
#                "GameEndDateTime": null,
#                "DateTimeUTC": "2025-09-04T20:10:00",
#                "RescheduledFromGameID": null,
#                "SuspensionResumeDay": null,
#                "SuspensionResumeDateTime": null,
#                "SeriesInfo": null
#            },
#        ...]
#        """
#        date = SportDate.new()
#        season = str(date)
#        url = f"{self.base_url}/ScoresBasic/{season}?key={self.api_key}"
#        await get_data(client, url)
#        # TODO: Parse events
#        return []


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
#            base_url=settings.providers.sports.sportsdata.get(
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
#        standings_url = f"{self.base_url}/Standings/{self.name.lower()}?key={self.api_key}"
#        response = await self.client.get(standings_url)
#        response.raise_for_status()
#        raw_data = response.json()
#        for round in raw_data:
#            pass
#        return
#
#
# class UCL(Sport):
#    """UEFA Champions League"""
#
#    term_filter: list[str] = ["a", "club", "the", "football", "fc"]
#
#    def __init__(self, *args, **kwargs):
#        name = self.__class__.__name__
#        super().__init__(
#            settings=settings,
#            name=name,
#            base_url=settings.providers.sports.sportsdata.get(
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
#    async def get_teams(self) -> dict[str, Team]:
#        """Fetch the Standings data: (4 hour interval)"""
#        # e.g.
#        # https://api.sportsdata.io/v4/soccer/scores/json/Teams/ucl?key=
#        # Sample:
#        """
#        [
#        {
#            "TeamId": 509,
#            "AreaId": 68,
#            "VenueId": 2,
#            "Key": "ARS",
#            "Name": "Arsenal FC",
#            "FullName": "Arsenal Football Club ",
#            "Active": true,
#            "AreaName": "England",
#            "VenueName": "Emirates Stadium",
#            "Gender": "Male",
#            "Type": "Club",
#            "Address": null,
#            "City": null,
#            "Zip": null,
#            "Phone": null,
#            "Fax": null,
#            "Website": "http://www.arsenal.com",
#            "Email": null,
#            "Founded": 1886,
#            "ClubColor1": "Red",
#            "ClubColor2": "White",
#            "ClubColor3": null,
#            "Nickname1": "The Gunners",
#            "Nickname2": null,
#            "Nickname3": null,
#            "WikipediaLogoUrl": "https://upload.wikimedia.org/wikipedia/en/5/53/Arsenal_FC.svg",
#            "WikipediaWordMarkUrl": null,
#            "GlobalTeamId": 90000509
#        },
#        ...
#        ]
#        """
#        url = f"{self.base_url}/Teams/{self.name.lower()}?key={self.api_key}"
#        await get_data(self.client, url)
#
#    async def get_events(self, teams: dict[Team]):
#        """Fetch the current scores for the date for this sport. (5min interval)"""
#        # https://api.sportsdata.io/v4/soccer/scores/json/SchedulesBasic/ucl/2025?key=
#
#        # Sample:
#        """
#        [
#        {
#            "GameId": 79507,
#            "RoundId": 1499,
#            "Season": 2025,
#            "SeasonType": 3,
#            "Group": null,
#            "AwayTeamId": 587,
#            "HomeTeamId": 2776,
#            "VenueId": 9953,
#            "Day": "2024-07-09T00:00:00",
#            "DateTime": "2024-07-09T15:30:00",
#            "Status": "Final",
#            "Week": null,
#            "Winner": "HomeTeam",
#            "VenueType": "Home Away",
#            "AwayTeamKey": "HJK",
#            "AwayTeamName": "Helsingin JK",
#            "AwayTeamCountryCode": "FIN",
#            "AwayTeamScore": 0,
#            "AwayTeamScorePeriod1": 0,
#            "AwayTeamScorePeriod2": 0,
#            "AwayTeamScoreExtraTime": null,
#            "AwayTeamScorePenalty": null,
#            "HomeTeamKey": "PAN",
#            "HomeTeamName": "FK Panevėžys",
#            "HomeTeamCountryCode": "LTU",
#            "HomeTeamScore": 3,
#            "HomeTeamScorePeriod1": 1,
#            "HomeTeamScorePeriod2": 2,
#            "HomeTeamScoreExtraTime": null,
#            "HomeTeamScorePenalty": null,
#            "Updated": "2024-07-10T05:46:08",
#            "UpdatedUtc": "2024-07-10T09:46:08",
#            "GlobalGameId": 90079507,
#            "GlobalAwayTeamId": 90000587,
#            "GlobalHomeTeamId": 90002776,
#            "IsClosed": true,
#            "PlayoffAggregateScore": null
#        },
#        """
#        date = datetime.year
#        url = f"{self.base_url}/SchedulesBasic/{self.name.lower()}/{date}?key={self.api_key}"
#        data = await get_data(self.client, url)
#        start_window = datetime.now() - timedelta(days=-7)
#        end_window = datetime.now() + timedelta(days=7)
#        recent_events = []
#        for raw in data:
#            event_date = datetime.fromisoformat(raw.get("DateTime"))
#            if start_window <= event_date <= end_window:
#                try:
#                    event = Event(
#                        sport=self,
#                        date=event_date,
#                        home_team=self.team_key(raw.get("HomeTeamKey")),
#                        away_team=self.team_key(raw.get("AwayTeamKey")),
#                        home_score=int(raw.get("HomeTeamScore")),
#                        away_score=int(raw.get("AwayTeamScore")),
#                        status=raw.get("status"),
#                    )
#                    recent_events.append(event)
#                except SportsDataWarning:
#                    continue
#        return recent_events
#
