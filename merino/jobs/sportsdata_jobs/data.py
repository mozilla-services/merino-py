"""Sport Data constructs. These are used by both `job` and `suggest`"""

import json
import logging
from abc import abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Any

from dynaconf.base import Settings
from elasticsearch import Elasticsearch
from pydantic import BaseModel

from merino.configs import settings
from merino.utils.http_client import create_http_client
from merino.jobs.sportsdata_jobs import TEAM_TTL_WEEKS
from merino.jobs.sportsdata_jobs.common import fetch_data, SportDate, GameStatus
from merino.jobs.sportsdata_jobs.data import Team, Event
from merino.jobs.sportsdata_jobs.errors import SportDataError, SportDataWarning
from merino.providers.suggest.sports import LOGGING_TAG


class DataStore:
    # Create two indices for now, one for the team data, the other for event data.
    team_index: str
    event_index: str
    meta_index: str
    client: Elasticsearch
    timeout_ms: str
    data: dict[str, Any] | None

    def __init__(self, settings: Settings) -> None:
        try:
            # This may collapse into one data store, but for now, store
            # teams and events separately. Teams will require "fuzzy" search
            # and events will have a more well defined key.
            self.client = Elasticsearch(
                hosts=[host.strip() for host in settings.hosts.split(",")],
                api_key=settings.api_key
                )
            self.timeout_ms = f"{settings.timeout_ms or 100}ms"
            for index in [self.meta_index, self.event_index, self.team_index]:
                self.client.indices.create(index=index)
            self.data = dict(
                active=[sport.trim() for sport in settings.sports.sports.split(",")],
            )
        except AttributeError as ex:
            logging.warning(f"{LOGGING_TAG}⚠️ Could not create DataStore pool: {ex}")
            raise SportDataError(f"No Connection Pool: {ex}")
        logging.info(f"{LOGGING_TAG} Connected to datastore {settings.sports.dsn}")

    async def active_sports(self) -> list[str]:
        if self.data:
            return self.data.get("active", [])
        return []

    async def store_teams(self, teams: list[Team], sport_name:str):
        """store the list of teams."""

        # TODO: convert to async transactions
        # Compose a queue of operations
        # ```
        #   {"index": { "_index" : $index}}
        #   { $data }
        # ```
        queue=[]
        # TODO: Chunk this? Will we have more than 5000 teams per sport?
        for team in teams:
            # this can be optimized:
            queue.append(f"""{"index":{"_index":"{self.team_index}"}}""")
            queue.append(team.as_str())
        #update the meta info for the sport teams.
        queue.append(f"""{"index":{"_index":"{self.meta_index}"}}""")
        queue.append(json.dumps(dict(
            sport_name=sport_name,
            updated=datetime.now(tz=timezone.utc).timestamp()
        )))
        result = self.client.bulk(
            index=self.team_index,
            body=[]
        )
        if "errors" in result:
            for error in result["errors"]:
                logging.error(f"{LOGGING_TAG}🚨 Could not store team: {sport_name} - {error}")
            raise SportDataError(f"Could not load teams for {sport_name}: {result["errors"]}")



    async def store_events(self, events: list[Event], teams:list[Team], sport_name:str):
        """Store the event as event:team:team"""
        queue = []
        for event in events:
            queue.append(f"""{"index":{"_index":"{self.event_index}"}}""")
            queue.append(event.as_str())
        for event in events:
            # TODO: just shove them into memory for now.

            db.set(f"event:{event.home_team}:{event.status}", event.as_str())
            db.set(f"event:{event.away_team}:{event.status}", event.as_str())

    async def get_events(self, words: str, context: list[str] | None = None) -> Team:
        """Scan the keywords to see if we have a match for either a city or team"""
        db = redis.Redis().from_pool(self.team_pool)
        for word in words.lower().split(",")
        teams = db.get(f"str:{word.strip()}")
        for team in teams:
            # SCAN 0 MATCH event:{team}:* count 3
            pass
        pass

    async def fetch_metadata(self, sport_name:str) -> dict[str, Any]:
        """Return the set of metadata for this sport"""
        return dict()

    async def update_metadata(self, sport_name:str, data:dict [str, Any]):
        """Store the metadata for the sport"""



class Sport(BaseModel):
    """Wrapper class for often used sport data"""

    # Handle to the data store
    store: DataStore
    # Name of the sport
    name: str
    # UTC Date for the season start
    season_start: datetime | None
    # UTC Date for the season end
    season_end: datetime | None
    # UTC for last update time.
    updated: datetime
    # Base URL for API calls.
    base_url: str
    # How long +/- for events
    event_ttl: timedelta

    def __init__(
        self,
        name: str,
        store: DataStore,
        api_key: str,
        is_active=False,
        updated: datetime = datetime.fromordinal(1),
    ):
        self.name = name
        self.store = store
        self.api_key = api_key
        self.is_active = is_active
        self.http_client = create_http_client(base_url="")
        self.updated = updated
        # Default base URL to use
        # This may be overridden in some cases.
        self.base_url = f"https://api.sportdata.io/v3/{name.lower()}/scores/json"
        self.event_ttl = timedelta(days=14)

    def team_key(self, short: str) -> str:
        """Construct the team key by prefixing the sport to the sport team key

        (e.g. for MLB San Francisco Giants, return "mlb:sf")
        """
        return f"{self.name.lower()}:{short.lower()}"

    # Simple SerDe constructs.
    @classmethod
    def parse(cls, store: DataStore, string: str):
        parsed = json.loads(string)
        self = cls(
            store=store,
            name=parsed.get("name"),
            is_active=parsed.get("is_active"),
            api_key=parsed.get("api_key"),
            updated=parsed.get("updated"),
        )
        return self

    def as_str(self) -> str:
        return json.dumps(
            dict(
                name=self.name,
                api_key=self.api_key,
                is_active=self.is_active,
                updated=self.updated.isoformat(),
            )
        )

    @abstractmethod
    async def get_events(self) -> list[Event]:
        """Get list of current and upcoming events"""

    @abstractmethod
    async def get_teams(self) -> list[Team]:
        """Get the list of currently active teams"""


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
    colors: list[str] | None
    # Last update time.
    updated: datetime
    # Team Data expiration date:
    ttl: int

    # SerDe methods
    @classmethod
    def parse(cls, sport: Sport, serialized: str):
        """Deserialize from JSON string"""
        struct = json.loads(serialized)
        data_sport = struct.get("key").split(":")[0]
        if not sport.name == data_sport:
            raise SportDataError(
                f"{LOGGING_TAG}: Wrong sport! Expected {sport.name}, found{data_sport}"
            )
        return cls(
            terms=struct.get("terms"),
            name=struct.get("name"),
            key=struct.get("key"),
            locale=struct.get("locale"),
            aliases=struct.get("aliases"),
            colors=struct.get("colors"),
            updated=struct.get("updated"),
            ttl=struct.get("ttl") or int((datetime.now() + timedelta(weeks=TEAM_TTL_WEEKS)).timestamp())
        )

    def as_str(self) -> str:
        """Serialize to JSON string"""
        return json.dumps(self)


class Event(BaseModel):
    # Reference to the associated Sport (DO NOT SERIALIZE!)
    sport: Sport
    # list of searchable terms for this event.
    terms: str
    # Event UTC start time
    date: datetime
    # the team key for the home team
    home_team: str
    # the team key for the away team
    away_team: str
    # Score for the "Home" team
    home_score: int
    # Score for the "Away" team
    away_score: int
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
        home_team = sport.team_key(parsed.get("home_team"))
        away_team = sport.team_key(parsed.get("away_team"))
        terms = f"""event {sport_name} {home_team} {away_team}"""
        ttl = (datetime.now(tz=timezone.utc) + timedelta(weeks=EVENT_TTL_WEEKS)).timestamp()
        self = cls(
            sport=sport,
            date=parsed.get("date"),
            terms=terms,
            home_team=home_team,
            away_team=away_team,
            home_score=parsed.get("home_score"),
            away_score=parsed.get("away_score"),
            status=GameStatus(parsed.get("status")),
            ttl = int(ttl)
        )
        return self

    def as_str(self) -> str:
        """Serialize to JSON string"""
        # TODO: Placeholder, strip the `Sport` field
        return json.dumps(dict(
            terms = self.terms,
            date=self.date,
            sport_name = self.sport.name,
            home_team = self.home_team,
            away_team = self.away_team,
            home_score = self.home_score,
            away_score = self.away_score,
            status = self.status,
        ))

    def suggest_text(self, away: Team, home: Team) -> str:
        """TODO: Event suggest format as JSON"""
        text = f"{away.name} at {home.name}"
        match self.status:
            case "Upcoming":
                text = f"{text} starts {self.date}"
            case "Final":
                text = f"{text} Final score: {self.away_score} - {self.home_score}"
            case _:
                text = f"{text} currently {self.away_score} - {self.home_score}"
        return text


class NFL(Sport):
    """National Football League"""

    def __init__(self, *args, **kwargs):
        super().__init__(name="NFL", *args, **kwargs)

    async def update(self, settings: Settings, store: DataStore):
        """NFL requires a nightly "Timeframe" lookup."""
        logging.debug(f"{LOGGING_TAG} Getting timeframe for {self.name} ")
        URL = f"{self.base_url}/Timeframes/current?key={self.api_key}"
        response = await self.http_client.get(url=URL)
        response.raise_for_status()
        data = json.loads(response.content)
        # TODO: parse this out to get the current week and games.
        # see: https://sportsdata.io/developers/api-documentation/nfl#timeframesepl

    def event_ttl(self):
        return timedelta(days=7)


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
        data = await fetch_data(self.http_client, url)
        # TODO: Parse events
        return []

    async def update(self, store: DataStore):
        # TODO: Fill in update
        pass


class NBA(Sport):
    """National Basketball Association"""

    def __init__(self, *args, **kwargs):
        super().__init__(name="NBA", *args, **kwargs)
        self.event_ttl = timedelta(days=3)

    async def update(self, store: DataStore):
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
    term_filter:list [str] = ["a", "club", "the", "football", "fc"]

    def __init__(self, *args, **kwargs):
        super().__init__(name="EPL", *args, **kwargs)
        # EPL is a league beneath the general "soccer" sport.
        self.base_url = f"https://api.sportsdata.io/v4/soccer/scores/json"

    async def update(self, store: DataStore):
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
    term_filter:list [str] = ["a", "club", "the", "football", "fc"]
    storage: DataStore

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
        data = await fetch_data(self.http_client, url)
        teams = {}}
        for team_data in data:
            # build the list of terms we want to search:
            terms = set()
            for item in ["Name", "FullName", "AreaName", "City", "Nickname1", "Nickname2", "Nickname3"]:
                candidate = team_data.get(item)
                if candidate:
                    for word in list(" ".split(candidate)):
                        lword = word.lower()
                        if word not in self.term_filter:
                            terms.add(lword)
            team = Team(
                terms= " ".join(terms),
                key=self.team_key(team_data.get("Key")),
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
                ttl
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
            teams.append(team)
        return teams

    async def get_events(self):
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
        data = await fetch_data(self.http_client, url)
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
