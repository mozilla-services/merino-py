# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the log_data_creator.py utility module."""

from datetime import datetime, timezone
from typing import Any

import pytest
from pydantic import ValidationError
from starlette.requests import Request
from starlette.types import Message

from merino.middleware import ScopeKey
from merino.middleware.geolocation import Location
from merino.middleware.user_agent import UserAgent
from merino.utils.log_data_creators import (
    LogDataModel,
    SuggestLogDataModel,
    create_suggest_log_data,
)


@pytest.mark.parametrize(
    [
        "query",
        "expected_query",
        "expected_sid",
        "expected_client_variants",
        "expected_providers",
        "expected_seq",
    ],
    [
        (b"", None, None, "", "", None),
        (
            b"q=nope&sid=9aadf682-2f7a-4ad1-9976-dc30b60451d8",
            "nope",
            "9aadf682-2f7a-4ad1-9976-dc30b60451d8",
            "",
            "",
            None,
        ),
        (b"q=nope&client_variants=foo,bar", "nope", None, "foo,bar", "", None),
        (b"q=nope&providers=testprovider", "nope", None, "", "testprovider", None),
        (b"q=nope&seq=0", "nope", None, "", "", 0),
        (b"q=nope&seq=hello", "nope", None, "", "", None),
    ],
    ids=[
        "no_query",
        "query_with_sid",
        "query_with_client_variants",
        "query_with_providers",
        "query_with_seq",
        "query_with_no_numeric_seq",
    ],
)
def test_create_suggest_log_data(
    query: bytes,
    expected_query: str,
    expected_sid: str | None,
    expected_client_variants: str,
    expected_providers: str,
    expected_seq: int | None,
) -> None:
    """Test that the create_suggest_log_data method properly constructs log data given
    different query parameters.
    """
    location: Location = Location(
        country="US",
        regions=["WA"],
        city="Milton",
        dma=819,
        postal_code="98354",
    )
    user_agent: UserAgent = UserAgent(
        browser="Firefox(103.0)", os_family="macos", form_factor="desktop"
    )
    expected_log_data: SuggestLogDataModel = SuggestLogDataModel(
        sensitive=True,
        errno=0,
        time=datetime(1998, 3, 31),
        path="/api/v1/suggest",
        method="GET",
        query=expected_query,
        code=200,
        rid="1b11844c52b34c33a6ad54b7bc2eb7c7",
        session_id=expected_sid,
        sequence_no=expected_seq,
        client_variants=expected_client_variants,
        requested_providers=expected_providers,
        country=location.country,
        region=location.regions[0] if location.regions else None,
        city=location.city,
        dma=location.dma,
        browser=user_agent.browser,
        os_family=user_agent.os_family,
        form_factor=user_agent.form_factor,
    )

    request: Request = Request(
        scope={
            "type": "http",
            "headers": [],
            "method": "GET",
            "path": "/api/v1/suggest",
            "query_string": query,
            ScopeKey.GEOLOCATION: location,
            ScopeKey.USER_AGENT: user_agent,
        }
    )
    message: Message = {
        "type": "http.response.start",
        "status": 200,
        "headers": [
            (b"content-length", b"119"),
            (b"content-type", b"application/json"),
            (b"x-request-id", b"1b11844c52b34c33a6ad54b7bc2eb7c7"),
            (b"access-control-expose-headers", b"X-Request-ID"),
        ],
    }
    dt: datetime = datetime(1998, 3, 31)

    log_data: SuggestLogDataModel = create_suggest_log_data(request, message, dt)

    assert log_data == expected_log_data


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
