import json
import logging
from datetime import datetime, timedelta

from dynaconf.base import LazySettings
from pydantic import BaseModel
from redis import ConnectionPool, ConnectionError, Redis, RedisError
from typing import Any

from merino.utils.http_client import create_http_client
from merino.jobs.sportsdata_jobs.common import SportDate, SportDataError, DataStore
from merino.providers.suggest.sports import LOGGING_TAG
from merino.providers.suggest.sports.backends import SportSuggestion
