"""Utilities for Dynamic Wikipedia indexer job"""

import csv
from io import StringIO
from logging import Logger

import requests

# Timeout for downloading the category blocklist.
BLOCKLIST_TIMEOUT = 60


class ProgressReporter:
    """Report progress via logs"""

    logger: Logger
    action: str
    source: str
    destination: str
    total: int
    progress: int

    def __init__(self, logger: Logger, action: str, source: str, destination: str, total: int):
        self.logger = logger
        self.action = action
        self.source = source
        self.destination = destination
        self.total = total
        self.progress = 0

    def report(self, completed: int, blocked: int = 0):
        """Log the completed progress as it advances"""
        next_progress = round((completed + blocked) / self.total * 100)
        if next_progress != self.progress:
            self.progress = next_progress
            self.logger.info(
                f"{self.action} progress: {self.progress}%",
                extra={
                    "source": self.source,
                    "destination": self.destination,
                    "percent_complete": self.progress,
                    "completed": completed,
                    "total_size": self.total,
                    "blocked": blocked,
                },
            )


def create_blocklist(blocklist_file_url: str) -> set[str]:
    """Create the category blocklist from an external file url."""
    resp = requests.get(blocklist_file_url, timeout=BLOCKLIST_TIMEOUT)  # nosec
    resp.raise_for_status()
    csv_reader = csv.DictReader(StringIO(resp.text), delimiter=",")
    return set(row["name"] for row in csv_reader)
