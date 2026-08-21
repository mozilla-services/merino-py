"""Util scripts for merino jobs."""

import math


def pretty_file_size(bytes_len: int) -> str:
    """Convert an int to a pretty human-readable size with units abbreviation.
    Units are metric, not binary, e.g., KB instead of KiB.

    """
    units = ["bytes", "KB", "MB", "GB"]
    exp = min(int(math.floor(math.log(bytes_len, 1_000))), len(units) - 1)
    value = bytes_len / math.pow(1_000, exp)
    return f"{value:g} {units[exp]}"
