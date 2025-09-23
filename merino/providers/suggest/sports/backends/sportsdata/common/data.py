"""Data Types for Sports"""

# from __future__ import annotations

import asyncio
import copy
import json
import logging

import pdb

from abc import abstractmethod
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any, Final

from dynaconf.base import LazySettings
from elasticsearch import AsyncElasticsearch, BadRequestError
from httpx import AsyncClient
from pydantic import BaseModel

from merino.configs import settings
from merino.exceptions import BackendError
from merino.providers.suggest.sports import (
    LOGGING_TAG,
    TEAM_TTL_WEEKS,
    EVENT_TTL_WEEKS,
    ttl_from_now,
)
from merino.providers.suggest.sports.backends import get_data
from merino.providers.suggest.sports.backends.sportsdata.common import GameStatus
from merino.providers.suggest.sports.backends.sportsdata.common.error import (
    SportDataError,
    SportDataWarning,
)

SUGGEST_ID: Final[str] = "suggest-on-title"
MAX_SUGGESTIONS: Final[int] = settings.providers.sports.max_suggestions
TIMEOUT_MS: Final[str] = f"{settings.providers.sports.es.request_timeout_ms}ms"


class LocalDataStore:
    lock: asyncio.Lock
    data: dict[str, Any]

    def __init__(self):
        self.lock = asyncio.Lock()
        self.data = {}

    async def update(self, data: dict[str, Any]):
        async with self.lock:
            copy.deepcopy(data, self.data)

    async def find(self, key: str) -> dict[str, Any] | None:
        async with self.lock:
            return self.data.get(key)


# TODO: break this into it's own file?
class ElasticBackendError(BackendError):
    """General error with Elastic Search"""


# TODO: Eventually wrap this with DataStore
class ElasticDataStore:
    platform: str
    client: AsyncElasticsearch
    meta_index: str
    team_index: str

    def __init__(self, *, settings: LazySettings) -> None:
        """Initialize a connection to ElasticSearch"""
        dsn = settings.providers.sports.es.dsn
        self.client = AsyncElasticsearch(
            dsn, api_key=settings.providers.sports.es.api_key
        )
        # build the index based on the platform.
        self.platform = f"{{lang}}_{settings.sports.get("platform", "sports")}"
        self.meta_index = settings.sports.get("meta_index", f"{self.platform}_meta")
        self.team_index = settings.sports.get("team_index", f"{self.platform}_team")
        self.data = dict(
            active=[
                sport.strip() for sport in settings.providers.sports.sports.split(",")
            ],
        )
        logging.info(f"{LOGGING_TAG} Initialized Elastic search at {dsn}")

    async def build_indexes(self, settings: LazySettings):
        """ "Indicies are created externally by terraform.
        Build them here for stand-alone and testing reasons.
        """
        dsn = settings.providers.sports.es.dsn
        for lang in ["en"]:
            for index in [self.meta_index, self.team_index]:
                try:
                    await self.client.indices.create(index=index.format(lang=lang))
                except BadRequestError as ex:
                    if ex.error == "resource_already_exists_exception":
                        logging.debug(
                            f"{LOGGING_TAG}🐜 {index.format(lang=lang)} already exists, skipping"
                        )
                        continue
                    pdb.set_trace()
                    print(ex)

    async def shutdown(self):
        await self.client.close()

    async def search(self, q: str, language_code: str) -> list[dict[str, Any]]:
        """Search based on the language and platform template"""
        index_id = self.platform.format(lang=language_code)

        suggest = {
            SUGGEST_ID: {
                "prefix": q,
                "completion": {"field": "terms", "size": MAX_SUGGESTIONS},
            }
        }

        try:
            res = await self.client.search(
                index=index_id,
                suggest=suggest,
                timeout=TIMEOUT_MS,
                source_includes=["team_key"],
            )
        except Exception as ex:
            raise BackendError(
                f"{LOGGING_TAG}🚨 Elasticsearch error for {index_id}: {ex}"
            ) from ex

        if "suggest" in res:
            # TODO: filter out duplicate events.
            return [doc for doc in res["suggest"][SUGGEST_ID][0]["options"]]
        else:
            return []

    async def store_teams(
        self, teams: list["Team"], sport_name: str, lang_code: str = "en"
    ):
        """Optionally store the list of teams in Elastic Search.
        Teams should be held in local memory."""

        # TODO: convert to async transactions
        # Compose a queue of operations
        # ```
        #   {"index": { "_index" : $index}}
        #   { $data }
        # ```
        queue = []
        # TODO: Chunk this? Will we have more than 5000 teams per sport?
        team_idx = self.team_index.format(lang=lang_code)
        meta_idx = self.meta_index.format(lang=lang_code)
        for team in teams:
            idx = self.team_index.format(lang=lang_code)
            # this can be optimized:
            queue.append(f"""{"index":{"_index":"{team_idx}"}}""")
            queue.append(team.as_str())
        # update the meta info for the sport teams.
        queue.append(f"""{"index":{"_index":"{meta_idx}"}}""")
        queue.append(
            json.dumps(
                dict(
                    sport_name=sport_name,
                    updated=datetime.now(tz=timezone.utc).timestamp(),
                )
            )
        )
        pdb.set_trace()
        result = self.client.bulk(index=team_idx, body=[])
        if "errors" in result:
            for error in result["errors"]:
                logging.error(
                    f"{LOGGING_TAG}🚨 Could not store team: {sport_name} - {error}"
                )
            raise SportDataError(
                f"Could not load teams for {sport_name}: {result["errors"]}"
            )

    async def store_events(
        self, events: list["Event"], teams: list["Team"], sport_name: str
    ):
        """Store the event as event:home_team:away_team"""
        event_data = {}

        for event in events:
            # TODO: just shove them into memory for now.
            event_data[f"event:{event.home_team}:{event.status}"] = event.as_str()
            event_data[f"event:{event.away_team}:{event.status}"] = event.as_str()

    async def store(
        self,
        language_code: str,
        doc: dict[str, Any],
    ) -> bool:
        # Iterate over the docs and store them internally.
        pass


class SportDate:
    instance: datetime
    """Return the current date in SportsData compliant format"""

    def __init__(self):
        self.instance = datetime.now()
        pass

    def __str__(self) -> str:
        return self.instance.strftime("%Y-%b-%d")

    def parse(self, parse: str):
        self.instance = datetime.strptime(parse, "%Y-%b-%d")


# TODO: refactor up to `.../sports`?
class Team(BaseModel):
    # Search terms for elastic search
    terms: str
    #  Team long name
    name: str
    # Team sport specific unique key
    key: str
    # Location of the team (city, state | country) if available
    locale: str | None
    # Alternate names for the team
    aliases: list[str]
    # Team colors (from primary to tertiary )
    colors: list[str]
    # Last update time.
    updated: datetime
    # Team Data expiration date:
    ttl: int

    def as_str(self) -> str:
        """Serialize to JSON string"""
        return json.dumps(self)


class Sport(BaseModel):
    """Root Model for Sport data"""

    api_key: str
    name: str
    teams: dict[str, Team]
    base_url: str
    event_ttl: timedelta
    team_ttl: timedelta
    # Commented because Pydantic does not know how to generate a core schema
    # http_client: AsyncClient
    # event_store: ElasticDataStore
    term_filter: list[str]

    def __init__(self, settings: LazySettings, *args, **kwargs):
        logging.debug(f"{LOGGING_TAG} In sport")
        # Set defaults for overrides
        if "event_ttl" not in kwargs:
            kwargs.update(
                {
                    "event_ttl": timedelta(
                        weeks=settings.get("event_ttl_weeks", EVENT_TTL_WEEKS)
                    )
                }
            )
        if "team_ttl" not in kwargs:
            kwargs.update(
                {
                    "team_ttl": timedelta(
                        weeks=settings.get("team_ttl_weeks", TEAM_TTL_WEEKS)
                    )
                }
            )
        if "term_filter" not in kwargs:
            kwargs.update({"term_filter": []})
        super().__init__(
            *args,
            **kwargs,
        )

    def gen_key(self, key: str) -> str:
        return f"{self.name.lower()}:{key.lower()}"

    @abstractmethod
    def get_team(self, key: str) -> Team:
        """Return the team based on the key provided"""

    @abstractmethod
    async def update_teams(self, client: AsyncClient):
        """Update team information and store in common storage (usually called nightly)"""

    @abstractmethod
    async def update_events(self, client: AsyncClient):
        """Fetch the list of current and upcoming events for this sport"""

    def load_teams_from_source(self, data: list[dict[str, Any]]) -> dict[str, Team]:
        """Create the Team entries from the data source

        This presumes that we are receiving data that complies with the SportsData.io
        `Team` data dictionary (See https://sportsdata.io/developers/data-dictionary/nfl#team)

        If we ever have a different data provider, this will need to be moved to the
        SportData provider class.
        """
        for team_data in data:
            # build the list of terms we want to search:
            terms = set()
            for item in [
                "Name",
                "AreaName",
                "City",
                "FullName",
                "Nickname1",
                "Nickname2",
                "Nickname3",
            ]:
                candidate = team_data.get(item)
                if candidate:
                    for word in list(candidate.split(" ")):
                        lword = word.lower()
                        if word not in self.term_filter:
                            terms.add(lword)
            logging.debug(f"{LOGGING_TAG} - Team: {team_data.get("Name")}")
            team = Team(
                terms=" ".join(terms),
                key=self.gen_key(team_data["Key"]),
                name=team_data.get("FullName", team_data["Name"]),
                locale=" ".join(
                    [team_data.get("City", ""), team_data.get("AreaName", "")]
                ).strip(),
                aliases=list(
                    filter(
                        lambda x: x is not None,
                        [
                            team_data.get("FullName"),
                            # Not all teams have nicknames,
                            team_data.get("Nickname1"),
                            team_data.get("Nickname2"),
                            team_data.get("Nickname3"),
                        ],
                    )
                ),
                updated=datetime.now(),
                ttl=ttl_from_now(self.team_ttl),
                colors=list(
                    filter(
                        lambda x: x is not None,
                        [
                            # Some Teams use "ClubColor#"
                            team_data.get("PrimaryColor"),
                            team_data.get("SecondaryColor"),
                            team_data.get("TertiaryColor"),
                            team_data.get("QuaternaryColor"),
                        ],
                    )
                ),
            )
            self.teams[team.key] = team
        return self.teams

    def load_events_from_source(self, data: list[dict[str, Any]]) -> list["Event"]:
        """ "Scan the list of events for any event within the 'current' window.

        This presumes that we are receiving data that complies with the SportsData.io
        `Team` data dictionary (See https://sportsdata.io/developers/data-dictionary/nfl#team)

        If we ever have a different data provider, this will need to be moved to the
        SportData provider class.

        """
        return []


class Event(BaseModel):
    """Root model for a Sporting Event (e.g. a game or match)"""

    # Reference to the associated Sport (DO NOT SERIALIZE!)
    sport: Sport
    # list of searchable terms for this event.
    terms: str
    # Event UTC start time
    date: datetime
    # the team key for the home team
    home_team: dict[str, str | list[str]]
    # the team key for the away team
    away_team: dict[str, str | list[str]]
    # Score for the "Home" team
    home_score: int | None
    # Score for the "Away" team
    away_score: int | None
    # Status of the game
    status: GameStatus
    # How long to retain an event in seconds
    ttl: int

    @classmethod
    def parse(cls, sport: Sport, serialized: str):
        """Deserialize from JSON string"""
        parsed = json.loads(serialized)
        sport_name = parsed.get("sport_name")
        if sport_name != sport.name:
            raise SportDataError(
                f"Conflicting team name found in storage: {sport_name}"
            )
        try:
            status = GameStatus(parsed.get("status"))
        except ValueError as ex:
            logging.debug(
                f"""{LOGGING_TAG}⚠️ Unknown status: {parsed.get("status")}, ignoring"""
            )
            raise SportDataWarning("Unknown game status, ignoring")
        home_team = sport.get_team(parsed.get("home_team"))
        away_team = sport.get_team(parsed.get("away_team"))
        terms = f"""event {sport_name} {home_team} {away_team}"""
        ttl = ttl_from_now(sport.event_ttl)
        self = cls(
            sport=sport,
            date=parsed.get("date"),
            terms=terms,
            home_team=dict(
                key=home_team.key, name=home_team.name, colors=home_team.colors
            ),
            away_team=dict(
                key=away_team.key, name=away_team.name, colors=away_team.colors
            ),
            home_score=parsed.get("home_score"),
            away_score=parsed.get("away_score"),
            status=GameStatus(parsed.get("status")),
            ttl=ttl,
        )
        return self

    def as_str(self) -> str:
        """Serialize to JSON string"""
        # TODO: Placeholder, strip the `Sport` field
        return json.dumps(
            dict(
                terms=self.terms,
                date=self.date,
                sport_name=self.sport.name,
                home_team=self.home_team,
                away_team=self.away_team,
                home_score=self.home_score,
                away_score=self.away_score,
                status=self.status,
            )
        )

    def suggest_text(self, away: Team, home: Team) -> str:
        """TODO: Event suggest format as JSON"""
        text = f"{away.name} at {home.name}"
        match self.status:
            case GameStatus.Scheduled | GameStatus.Delayed:
                text = f"{text} starts {self.date}"
            case GameStatus.Final | GameStatus.F_OT:
                text = f"{text} Final score: {self.away_score} - {self.home_score}"
            case _:
                text = f"{text} {self.status.as_str()}: {self.away_score} - {self.home_score}"
        return text


class NFL(Sport):
    """National Football League"""

    season: str | None
    week: int | None
    teams: dict[str, Team]
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
            week=None,
            teams={},
            team_ttl=timedelta(weeks=4),
            _lock=asyncio.Lock(),
            *args,
            **kwargs,
        )
        # self.event_ttl = timedelta(weeks=2)
        # self.team_ttl = timedelta(weeks=52)

    async def get_team(self, name: str) -> Team | None:
        async with self._lock:
            return self.teams.get(self.gen_key(name))

    async def update_teams(self, http_client: AsyncClient):
        """NFL requires a nightly "Timeframe" lookup."""
        # see: https://sportsdata.io/developers/api-documentation/nfl#timeframesepl
        logging.debug(f"{LOGGING_TAG} Getting timeframe for {self.name} ")
        url = f"{self.base_url}/Timeframes/current?key={self.api_key}"
        response = await get_data(client=http_client, url=url)
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
        # Now get the team information:
        url = f"{self.base_url}/Teams?key={self.api_key}"
        pdb.set_trace()
        response = await get_data(client=http_client, url=url)
        self.load_teams_from_source(response)
        print(response)
        # store to elastic search

    async def update_events(self, http_client: AsyncClient):
        logging.debug(f"{LOGGING_TAG} Getting Events for {self.name}")
        pdb.set_trace()
        url = (
            f"{self.base_url}/ScoresBasic/{self.season}/{self.week}?key={self.api_key}"
        )
        response = await get_data(client=http_client, url=url)
        print(response)
        # TODO: Store to thread locked memory.


class MLB(Sport):
    """Major League Baseball"""

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
            week=None,
            teams={},
            _lock=asyncio.Lock(),
            *args,
            **kwargs,
        )

    async def get_events(self) -> list[Event]:
        """Fetch the list of events for the sport. (5 min interval)"""
        # https://api.sportsdata.io/v3/mlb/scores/json/teams?key=
        # Sample:
        """
        [
            {
                "AwayTeamRuns": 0,
                "HomeTeamRuns": 0,
                "AwayTeamHits": 2,
                "HomeTeamHits": 5,
                "AwayTeamErrors": 0,
                "HomeTeamErrors": 0,
                "Attendance": null,
                "GlobalGameID": 10076415,
                "GlobalAwayTeamID": 10000012,
                "GlobalHomeTeamID": 10000032,
                "NeutralVenue": false,
                "Inning": 4,
                "InningHalf": "B",
                "GameID": 76415,
                "Season": 2025,
                "SeasonType": 1,
                "Status": "InProgress",
                "Day": "2025-09-04T00:00:00",
                "DateTime": "2025-09-04T16:10:00",
                "AwayTeam": "PHI",
                "HomeTeam": "MIL",
                "AwayTeamID": 12,
                "HomeTeamID": 32,
                "RescheduledGameID": null,
                "StadiumID": 92,
                "IsClosed": false,
                "Updated": "2025-09-04T17:19:20",
                "GameEndDateTime": null,
                "DateTimeUTC": "2025-09-04T20:10:00",
                "RescheduledFromGameID": null,
                "SuspensionResumeDay": null,
                "SuspensionResumeDateTime": null,
                "SeriesInfo": null
            },
        ...]
        """
        season = SportDate()
        url = f"{self.base_url}/ScoresBasic/{season}?key={self.api_key}"
        data = await get_data(self.http_client, url)
        # TODO: Parse events
        return []


class NBA(Sport):
    """National Basketball Association"""

    def __init__(self, settings: LazySettings, *args, **kwargs):
        name = self.__class__.__name__
        super().__init__(
            settings=settings,
            name=name,
            base_url=settings.providers.sports.sportsdata.get(
                "base_url",
                default=f"https://api.sportsdata.io/v3/{name.lower()}/scores/json/",
            ),
            season=None,
            week=None,
            teams={},
            team_ttl=timedelta(weeks=4),
            event_ttl=timedelta(days=3),
            _lock=asyncio.Lock(),
            *args,
            **kwargs,
        )


class NHL(Sport):
    """Major Hockey League"""

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
            week=None,
            teams={},
            _lock=asyncio.Lock(),
            *args,
            **kwargs,
        )


class EPL(Sport):
    """English Premier League"""

    term_filter: list[str] = ["a", "club", "the", "football", "fc"]

    def __init__(self, settings: LazySettings, *args, **kwargs):
        name = self.__class__.__name__

        super().__init__(
            settings=settings,
            name=name,
            base_url=settings.providers.sports.sportsdata.get(
                f"base_url.{name.lower()}",
                default=f"https://api.sportsdata.io/v3/soccer/scores/json/",
            ),
            season=None,
            week=None,
            teams={},
            _lock=asyncio.Lock(),
            *args,
            **kwargs,
        )

    async def update(self, store: ElasticDataStore):
        """Fetch and update the Team Standing information."""
        # TODO: Fill in update
        # fetch the Standings data: (5 min interval)
        """

        """
        standings_url = (
            f"{self.base_url}/Standings/{self.name.lower()}?key={self.api_key}"
        )
        response = await self.http_client.get(standings_url)
        response.raise_for_status()
        raw_data = response.json()
        for round in raw_data:
            pass
        return


class UCL(Sport):
    """UEFA Champions League"""

    term_filter: list[str] = ["a", "club", "the", "football", "fc"]

    def __init__(self, *args, **kwargs):
        name = self.__class__.__name__
        super().__init__(
            settings=settings,
            name=name,
            base_url=settings.providers.sports.sportsdata.get(
                f"base_url.{name.lower()}",
                default=f"https://api.sportsdata.io/v3/soccer/scores/json/",
            ),
            season=None,
            week=None,
            teams={},
            _lock=asyncio.Lock(),
            *args,
            **kwargs,
        )

    async def get_teams(self) -> dict[str, Team]:
        """fetch the Standings data: (4 hour interval)"""
        # e.g.
        # https://api.sportsdata.io/v4/soccer/scores/json/Teams/ucl?key=
        # Sample:
        """
        [
        {
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
        url = f"{self.base_url}/Teams/{self.name.lower()}?key={self.api_key}"
        data = await get_data(self.http_client, url)
        teams = {}

    async def get_events(self, teams: dict[Team]):
        """Fetch the current scores for the date for this sport. (5min interval)"""
        # https://api.sportsdata.io/v4/soccer/scores/json/SchedulesBasic/ucl/2025?key=

        # Sample:
        """
        [
        {
            "GameId": 79507,
            "RoundId": 1499,
            "Season": 2025,
            "SeasonType": 3,
            "Group": null,
            "AwayTeamId": 587,
            "HomeTeamId": 2776,
            "VenueId": 9953,
            "Day": "2024-07-09T00:00:00",
            "DateTime": "2024-07-09T15:30:00",
            "Status": "Final",
            "Week": null,
            "Winner": "HomeTeam",
            "VenueType": "Home Away",
            "AwayTeamKey": "HJK",
            "AwayTeamName": "Helsingin JK",
            "AwayTeamCountryCode": "FIN",
            "AwayTeamScore": 0,
            "AwayTeamScorePeriod1": 0,
            "AwayTeamScorePeriod2": 0,
            "AwayTeamScoreExtraTime": null,
            "AwayTeamScorePenalty": null,
            "HomeTeamKey": "PAN",
            "HomeTeamName": "FK Panevėžys",
            "HomeTeamCountryCode": "LTU",
            "HomeTeamScore": 3,
            "HomeTeamScorePeriod1": 1,
            "HomeTeamScorePeriod2": 2,
            "HomeTeamScoreExtraTime": null,
            "HomeTeamScorePenalty": null,
            "Updated": "2024-07-10T05:46:08",
            "UpdatedUtc": "2024-07-10T09:46:08",
            "GlobalGameId": 90079507,
            "GlobalAwayTeamId": 90000587,
            "GlobalHomeTeamId": 90002776,
            "IsClosed": true,
            "PlayoffAggregateScore": null
        },
        """
        date = datetime.year
        url = f"{self.base_url}/SchedulesBasic/{self.name.lower()}/{date}?key={self.api_key}"
        data = await get_data(self.http_client, url)
        start_window = datetime.now() - timedelta(days=-7)
        end_window = datetime.now() + timedelta(days=7)
        recent_events = []
        for raw in data:
            event_date = datetime.fromisoformat(raw.get("DateTime"))
            if start_window <= event_date <= end_window:
                try:
                    event = Event(
                        sport=self,
                        date=event_date,
                        home_team=self.team_key(raw.get("HomeTeamKey")),
                        away_team=self.team_key(raw.get("AwayTeamKey")),
                        home_score=int(raw.get("HomeTeamScore")),
                        away_score=int(raw.get("AwayTeamScore")),
                        status=raw.get("status"),
                    )
                    recent_events.append(event)
                except SportDataWarning:
                    continue
        return recent_events
