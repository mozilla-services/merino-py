import json
import logging
from datetime import datetime, timedelta

from dynaconf.base import LazySettings
from pydantic import BaseModel
from redis import ConnectionPool, ConnectionError, Redis, RedisError
from typing import Any

from merino.utils.http_client import create_http_client
