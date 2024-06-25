"""Utilities for Dynamic Wikipedia indexer job"""

import csv
from io import StringIO
from logging import Logger

import requests
from elasticsearch import Elasticsearch


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
    """Create blocklist from an external file url."""
    block_list = requests.get(blocklist_file_url).text  # nosec
    file_like_io = StringIO(block_list)
    csv_reader = csv.DictReader(file_like_io, delimiter=",")
    return set(row["name"] for row in csv_reader)


def create_elasticsearch_client(
    elasticsearch_url: str,
    elasticsearch_api_key: str,
) -> Elasticsearch:
    """Create the Elasticsearch client."""
    return Elasticsearch(
        elasticsearch_url,
        api_key=elasticsearch_api_key,
        request_timeout=60,
    )
