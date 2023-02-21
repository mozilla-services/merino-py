"""Utilities for wikipedia indexer job"""
from logging import Logger


class ProgressReporter:
    """Report progress via logs"""

    logger: Logger
    action: str
    source: str
    destination: str
    total: int
    progress: int

    def __init__(
        self, logger: Logger, action: str, source: str, destination: str, total: int
    ):
        self.logger = logger
        self.action = action
        self.source = source
        self.destination = destination
        self.total = total
        self.progress = 0

    def report(self, completed: int):
        """Log the completed progress as it advances"""
        next_progress = round(completed / self.total * 100)
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
                },
            )
