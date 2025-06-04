# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for __init__.py."""

from merino.jobs.utils import pretty_file_size


def test_pretty_file_size():
    """Test `pretty_file_size`"""
    assert pretty_file_size(1) == "1 bytes"
    assert pretty_file_size(999) == "999 bytes"
    assert pretty_file_size(1_000) == "1 KB"
    assert pretty_file_size(1_001) == "1.001 KB"
    assert pretty_file_size(999 * 1_000) == "999 KB"
    assert pretty_file_size(1_000 * 1_000) == "1 MB"
    assert pretty_file_size(1_001 * 1_000) == "1.001 MB"
    assert pretty_file_size(999 * 1_000 * 1_000) == "999 MB"
    assert pretty_file_size(1_000 * 1_000 * 1_000) == "1 GB"
    assert pretty_file_size(1_001 * 1_000 * 1_000) == "1.001 GB"
    assert pretty_file_size(999 * 1_000 * 1_000 * 1_000) == "999 GB"
    assert pretty_file_size(1_000 * 1_000 * 1_000 * 1_000) == "1000 GB"
    assert pretty_file_size(1_001 * 1_000 * 1_000 * 1_000) == "1001 GB"
