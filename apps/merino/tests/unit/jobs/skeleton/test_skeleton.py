# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Example Unit tests for jobs skeleton_uploader module.

**Note** Since the skeleton_uploader is mostly a no-op, so are
these tests. Your tests should try to replicate or emulate as much
functionality as possible to ensure that your tests continue to work,
as well as detect errors. Tests are important, not only for you, but
so that larger changes can be checked to ensure that there's no
fault with your code.

Merino requires >95% test coverage (combined unit and integration tests)
These tests _may_ also be to ensure that there is proper coverage.
"""

import pytest

from merino.jobs.skeleton_uploader import SkeletonError, SkeletonUploader

# Define your `@pytest.fixture()` here. See other unit tests for examples


@pytest.mark.asyncio
async def test_skeleton_uploader():
    """Test the uploader.

    You can pass the fixtures as arguments to this function. See the
    [pytest docs](https://docs.pytest.org/en/stable/) if you're unfamiliar
    with this.
    """
    error = SkeletonError("foo")
    assert error.msg == "foo"

    uploader = SkeletonUploader("foobar")
    assert uploader.auth == "foobar"
    assert uploader.load_data()
