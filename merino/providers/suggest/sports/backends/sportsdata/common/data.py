"""Data Types for Sports"""

import asyncio
import copy
import json
import logging

from abc import abstractmethod
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any, Final

from dynaconf.base import LazySettings
from elasticsearch import AsyncElasticsearch
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
from merino.providers.suggest.sports.backends.sportsdata.common.data import Team
from merino.providers.suggest.sports.backends.sportsdata.common.error import (
    SportDataError,
    SportDataWarning,
)

SUGGEST_ID: Final[str] = "suggest-on-title"
MAX_SUGGESTIONS: Final[int] = settings.providers.sports.max_suggestions
TIMEOUT_MS: Final[str] = f"{settings.providers.sports.request_timeout_ms}ms"


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
        dsn = settings.sports["dsn"]
        self.client = AsyncElasticsearch(dsn, api_key=settings.sports["api_key"])
        # build the index based on the platform.
        self.platform = f"{{lang}}_{settings.sports["platform"]}"
        self.meta_index = settings.get("meta_index", "sports_meta")
        self.team_index = settings.get("team_index", "sports_team")
        logging.info(f"{LOGGING_TAG} Initialized Elastic search at {dsn}")
        loop = asyncio.get_event_loop()
        for index in [self.meta_index, self.team_index]:
            loop.run_until_complete(self.client.indices.create(index=index))
        self.data = dict(
            active=[sport.trim() for sport in settings.sports.sports.split(",")],
        )

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
            return [doc for doc in res["suggest"][SUGGEST_ID][0]["options"]]
        else:
            return []

    async def store_teams(self, teams: list[Team], sport_name: str):
        """store the list of teams."""

        # TODO: convert to async transactions
        # Compose a queue of operations
        # ```
        #   {"index": { "_index" : $index}}
        #   { $data }
        # ```
        queue = []
        # TODO: Chunk this? Will we have more than 5000 teams per sport?
        for team in teams:
            # this can be optimized:
            queue.append(f"""{"index":{"_index":"{self.team_index}"}}""")
            queue.append(team.as_str())
        # update the meta info for the sport teams.
        queue.append(f"""{"index":{"_index":"{self.meta_index}"}}""")
        queue.append(
            json.dumps(
                dict(
                    sport_name=sport_name,
                    updated=datetime.now(tz=timezone.utc).timestamp(),
                )
            )
        )
        import pdb

        pdb.set_trace()
        result = self.client.bulk(index=self.team_index, body=[])
        if "errors" in result:
            for error in result["errors"]:
                logging.error(
                    f"{LOGGING_TAG}🚨 Could not store team: {sport_name} - {error}"
                )
            raise SportDataError(
                f"Could not load teams for {sport_name}: {result["errors"]}"
            )

    async def store_events(
        self, events: list[Event], teams: list[Team], sport_name: str
    ):
        """Store the event as event:team:team"""
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

    # SerDe methods
    @classmethod
    def parse(cls, sport_name: str, serialized: str):
        """Deserialize from JSON string"""
        struct = json.loads(serialized)
        data_sport = struct.get("key").split(":")[0]
        if not sport_name == data_sport:
            raise SportDataError(
                f"{LOGGING_TAG}: Wrong sport! Expected {sport_name}, found{data_sport}"
            )
        return cls(
            terms=struct.get("terms"),
            name=struct.get("name"),
            key=struct.get("key"),
            locale=struct.get("locale"),
            aliases=struct.get("aliases"),
            colors=struct.get("colors"),
            updated=struct.get("updated"),
            ttl=struct.get("ttl")
            or int((datetime.now() + timedelta(weeks=TEAM_TTL_WEEKS)).timestamp()),
        )

    def as_str(self) -> str:
        """Serialize to JSON string"""
        return json.dumps(self)


class Sport(BaseModel):
    """Root Model for Sport data"""

    api_key: str
    name: str
    http_client: AsyncClient
    teams: dict[str, Team]
    base_url: str
    event_ttl: timedelta
    team_ttl: timedelta
    event_store: ElasticDataStore

    def __init__(self, settings: LazySettings, *args, **kwargs):
        super().__init__(key=settings.get("key"), *args, **kwargs)
        self.base_url = settings.get(
            "base_url",
            default=f"https://api.sportsdata.io/v3/{self.name.lower()}/scores/json/",
        )
        self.event_store = ElasticDataStore(
            api_key=settings["api_key"], dsn=settings["dsn"]
        )
        self.event_ttl = timedelta(
            weeks=settings.get("event_ttl_weeks", EVENT_TTL_WEEKS)
        )
        self.team_ttl = timedelta(weeks=settings.get("team_ttl_weeks", TEAM_TTL_WEEKS))

    def gen_key(self, key: str) -> str:
        return f"{self.name}:{key}"

    @abstractmethod
    def get_team(self, key: str) -> Team:
        """Return the team based on the key provided"""

    @abstractmethod
    async def update_teams(self):
        """Update team information and store in common storage (usually called nightly)"""

    @abstractmethod
    async def update_events(self):
        """Fetch the list of current and upcoming events for this sport"""


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
            ttl=ttl_from_now(sport.event_ttl),
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

    season: str
    week: int
    teams: dict[str, Team]
    _lock: asyncio.Lock

    def __init__(self, *args, **kwargs):
        super().__init__(name="NFL", *args, **kwargs)
        self.teams = {}
        self.lock = asyncio.Lock()
        # self.event_ttl = timedelta(weeks=2)
        # self.team_ttl = timedelta(weeks=52)

    async def get_team(self, name: str) -> Team | None:
        async with self.lock:
            return self.teams.get(self.gen_key(name))

    async def update_teams(self):
        """NFL requires a nightly "Timeframe" lookup."""
        logging.debug(f"{LOGGING_TAG} Getting timeframe for {self.name} ")
        URL = f"{self.base_url}/Timeframes/current?key={self.api_key}"
        import pdb

        pdb.set_trace()
        response = await get_data(client=self.http_client, url=URL)
        print(response)
        # TODO: parse this out to get the current week and games.
        # see: https://sportsdata.io/developers/api-documentation/nfl#timeframesepl
        # store to elastic search

    async def update_events(self):
        logging.debug(f"{LOGGING_TAG} Getting Events for {self.name}")
        URL = (
            f"{self.base_url}/ScoresBasic/{self.season}/{self.week}?key={self.api_key}"
        )
        # TODO: fetch previous/upcoming week info?
        response = await get_data(client=self.http_client, url=URL)
        # TODO: Store to thread locked memory.


class MLB(Sport):
    """Major League Baseball"""

    def __init__(self, *args, **kwargs):
        super().__init__(name="MLB", *args, **kwargs)

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

    async def update(self, store: ElasticDataStore):
        # TODO: Fill in update
        pass


class NBA(Sport):
    """National Basketball Association"""

    def __init__(self, *args, **kwargs):
        super().__init__(name="NBA", *args, **kwargs)
        self.event_ttl = timedelta(days=3)

    async def update(self, store: ElasticDataStore):
        # TODO: Fill in update
        pass

        return timedelta(days=3)


class NHL(Sport):
    """Major Hockey League"""

    store: DataStore

    def __init__(self, *args, **kwargs):
        super().__init__(name="NHL", *args, **kwargs)

    async def update(self, store: DataStore):
        # TODO: Fill in update
        pass

        return timedelta(days=3)


class EPL(Sport):
    """English Premier League"""

    term_filter: list[str] = ["a", "club", "the", "football", "fc"]

    def __init__(self, *args, **kwargs):
        super().__init__(name="EPL", *args, **kwargs)
        # EPL is a league beneath the general "soccer" sport.
        self.base_url = f"https://api.sportsdata.io/v4/soccer/scores/json"

    async def update(self, store: ElasticDataStore):
        """Fetch and update the Team Standing information."""
        # TODO: Fill in update
        # fetch the Standings data: (5 min interval)
        """

        """
        standings_url = f"{self.base_url}/Standings/{self.name}?key={self.api_key}"
        response = await self.http_client.get(standings_url)
        response.raise_for_status()
        raw_data = response.json()
        for round in raw_data:
            pass
        return


class UCL(Sport):
    """UEFA Champions League"""

    term_filter: list[str] = ["a", "club", "the", "football", "fc"]
    storage: ElasticDataStore

    def __init__(self, *args, **kwargs):
        super().__init__(name="UCL", *args, **kwargs)
        self.base_url = f"https://api.sportsdata.io/v4/soccer/scores/json/"

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
        url = f"{self.base_url}/Teams/{self.name}?key={self.api_key}"
        data = await get_data(self.http_client, url)
        teams = {}
        for team_data in data:
            # build the list of terms we want to search:
            terms = set()
            for item in [
                "Name",
                "FullName",
                "AreaName",
                "City",
                "Nickname1",
                "Nickname2",
                "Nickname3",
            ]:
                candidate = team_data.get(item)
                if candidate:
                    for word in list(" ".split(candidate)):
                        lword = word.lower()
                        if word not in self.term_filter:
                            terms.add(lword)
            team = Team(
                terms=" ".join(terms),
                key=self.gen_key(team_data.get("Key")),
                name=team_data.get("Name"),
                locale=" ".join(
                    [team_data.get("City"), team_data.get("AreaName")]
                ).strip(),
                aliases=list(
                    filter(
                        lambda x: x is not None,
                        [
                            team_data.get("FullName"),
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
                            team_data.get("ClubColor1"),
                            team_data.get("ClubColor2"),
                            team_data.get("ClubColor3"),
                        ],
                    )
                ),
            )
            teams[team.key] = Team
        return teams

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
        date = SportDate()
        url = f"{self.base_url}/ScoresBasic/{date}?key={self.api_key}"
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

    async def update(self):
        """Fetch and update the Team information."""
        teams = await self.get_teams()
        # Note, soccer
        events = await self.get_events()
        await self.store.store_teams(teams, self.name)
        await self.store.store_events(events, teams, self.name)

        return timedelta(days=3)
