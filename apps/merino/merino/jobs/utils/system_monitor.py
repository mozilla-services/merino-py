"""Monitor hardware resources and open TCP connections"""

import psutil
import logging
import gc
from typing import Optional

logger = logging.getLogger(__name__)


class SystemMonitor:
    """Simple utility to monitor system resources during domain processing."""

    def __init__(self) -> None:
        """Initialize the system monitor."""
        self.process = psutil.Process()
        self.initial_metrics: Optional[dict] = None

    def collect_metrics(self) -> dict:
        """Collect current system metrics."""
        # Memory metrics
        memory_info = self.process.memory_info()
        memory_percent = self.process.memory_percent()

        # File descriptor metrics
        try:
            open_files = len(self.process.open_files())
        except Exception as e:
            logger.warning(f"Could not get open files count: {e}")
            open_files = -1

        # Network connection metrics
        try:
            connections = len(self.process.connections(kind="inet"))
        except Exception as e:
            logger.warning(f"Could not get connection count: {e}")
            connections = -1

        # Collect metrics
        metrics = {
            "rss_mb": memory_info.rss / (1024 * 1024),
            "vms_mb": memory_info.vms / (1024 * 1024),
            "memory_percent": memory_percent,
            "open_files": open_files,
            "connections": connections,
            "gc_objects": sum(gc.get_count()),
        }

        # Store initial metrics on first run
        if self.initial_metrics is None:
            self.initial_metrics = metrics.copy()

        return metrics

    def log_metrics(
        self, chunk_num: Optional[int] = None, total_chunks: Optional[int] = None
    ) -> None:
        """Log current system metrics."""
        metrics = self.collect_metrics()

        # Create chunk info prefix if available
        chunk_info = f"[Chunk {chunk_num}/{total_chunks}] " if chunk_num is not None else ""

        # Log the metrics
        logger.info(
            f"{chunk_info}System Metrics -"
            f"Memory: {metrics['rss_mb']:.2f} MB ({metrics['memory_percent']:.1f}%),"
            f"Files: {metrics['open_files']},"
            f"Connections: {metrics['connections']},"
            f"GC Objects: {metrics['gc_objects']}"
        )
