# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the suggest_logging.py models module."""

from datetime import datetime, timezone
from typing import Any

import pytest
from pydantic import ValidationError

from merino_common.models.suggest_logging import LogDataModel


@pytest.mark.parametrize(
    "time_input",
    ["not a datetime string", {"not", "a", "datetime", "object"}],
    ids=["invalid_string", "invalid_object_type"],
)
def test_create_log_object_fails_on_invalid_time(time_input: Any):
    """Test that `time` fails validation on invalid time input."""
    with pytest.raises(ValidationError):
        LogDataModel(
            errno=0,
            time=time_input,
            path="/",
            method="GET",
        )


@pytest.mark.parametrize("expected_time", ["2022-12-18T15:58:41+00:00"])
@pytest.mark.parametrize(
    "datetime_rep",
    [
        datetime(2022, 12, 18, hour=15, minute=58, second=41, tzinfo=timezone.utc),
    ],
    ids=["datetime_obj"],
)
def test_create_log_object_can_convert_time_to_isoformat(
    datetime_rep: datetime, expected_time: str
):
    """Ensure that `time` field correctly validates datetime inputs
    and outputs ISO format string.
    """
    log_data = LogDataModel(
        errno=0,
        time=datetime_rep,
        path="/",
        method="GET",
    )
    assert log_data.model_dump().get("time") == expected_time
