"""Shared test configuration for merino-fleece. Must set MERINO_FLEECE_ENV before any merino_fleece import."""

import os

os.environ.setdefault("MERINO_FLEECE_ENV", "testing")
