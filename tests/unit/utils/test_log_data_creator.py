# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the log data creator utility module."""

from datetime import datetime
from typing import Any

import pytest
from starlette.requests import Request
from starlette.types import Message

from merino.middleware import ScopeKey
from merino.middleware.geolocation import Location
from merino.middleware.user_agent import UserAgent
from merino.utils.log_data_creators import (
    create_request_summary_log_data,
    create_suggest_log_data,
)


@pytest.mark.parametrize(
    ["headers", "expected_agent", "expected_lang"],
    [
        ([], None, None),
        ([(b"user-agent", b"curl/7.84.0")], "curl/7.84.0", None),
        ([(b"accept-language", b"en-US")], None, "en-US"),
    ],
    ids=["no_headers", "user_agent_header", "accept_language_header"],
)
def test_create_request_summary_log_data(
    headers: list[tuple[bytes, bytes]],
    expected_agent: str | None,
    expected_lang: str | None,
) -> None:
    expected_log_data: dict[str, Any] = {
        "errno": 0,
        "time": "1998-03-31T00:00:00",
        "agent": expected_agent,
        "path": "/__heartbeat__",
        "method": "GET",
        "lang": expected_lang,
        "querystring": {},
        "code": "200",
    }
    request: Request = Request(
        scope={
            "type": "http",
            "headers": headers,
            "method": "GET",
            "path": "/__heartbeat__",
            "query_string": "",
        }
    )
    message: Message = {"type": "http.response.start", "status": "200"}
    dt: datetime = datetime(1998, 3, 31)

    log_data: dict[str, Any] = create_request_summary_log_data(request, message, dt)

    assert log_data == expected_log_data


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
    ],
    ids=[
        "no_query",
        "query_with_sid",
        "query_with_client_variants",
        "query_with_providers",
        "query_with_seq",
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
    location: Location = Location(
        country="US", region="WA", city="Milton", dma=819, postal_code="98354"
    )
    user_agent: UserAgent = UserAgent(
        browser="Firefox(103.0)", os_family="macos", form_factor="desktop"
    )
    expected_log_data: dict[str, Any] = {
        "sensitive": True,
        "errno": 0,
        "time": "1998-03-31T00:00:00",
        "path": "/api/v1/suggest",
        "method": "GET",
        "query": expected_query,
        "code": "200",
        "rid": "1b11844c52b34c33a6ad54b7bc2eb7c7",
        "session_id": expected_sid,
        "sequence_no": expected_seq,
        "client_variants": expected_client_variants,
        "requested_providers": expected_providers,
        "country": location.country,
        "region": location.region,
        "city": location.city,
        "dma": location.dma,
        "browser": user_agent.browser,
        "os_family": user_agent.os_family,
        "form_factor": user_agent.form_factor,
    }
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
        "status": "200",
        "headers": [
            (b"content-length", b"119"),
            (b"content-type", b"application/json"),
            (b"x-request-id", b"1b11844c52b34c33a6ad54b7bc2eb7c7"),
            (b"access-control-expose-headers", b"X-Request-ID"),
        ],
    }
    dt: datetime = datetime(1998, 3, 31)

    log_data: dict[str, Any] = create_suggest_log_data(request, message, dt)

    assert log_data == expected_log_data
