"""Tests for the geonames-uploader job."""

import pytest

# Register assert introspection for utils files.
pytest.register_assert_rewrite("tests.unit.jobs.geonames_uploader.geonames_utils")
