"""Utilities for the Wikipedia article blocklist job"""

import csv
from io import StringIO

import requests

# Timeout for downloading the category blocklist.
BLOCKLIST_TIMEOUT = 60


def create_blocklist(blocklist_file_url: str) -> set[str]:
    """Create the category blocklist from an external file url."""
    resp = requests.get(blocklist_file_url, timeout=BLOCKLIST_TIMEOUT)  # nosec
    resp.raise_for_status()
    csv_reader = csv.DictReader(StringIO(resp.text), delimiter=",")
    return set(row["name"] for row in csv_reader)
