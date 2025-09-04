"""Sport info provider"""

import logging

from abc import abstractmethod
from pydantic import BaseModel, HttpUrl
from typing import Protocol

from merino.providers.suggest.base import (
    BaseSuggestion,
)

from merino.providers.manifest.backends.protocol import ManifestData

from merino.jobs.sportsdata_jobs import LOGGING_TAG
