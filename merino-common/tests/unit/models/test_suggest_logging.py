# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the suggest_logging.py models module."""

import json
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest
from pydantic import ValidationError

from merino_common.models.suggest_logging import (
    MozlogDataModel,
    SanitizedSearchTermLog,
    SuggestLogDataModel,
    SuggestRequestParams,
)


@pytest.mark.parametrize(
    "time_input",
    ["not a datetime string", {"not", "a", "datetime", "object"}],
    ids=["invalid_string", "invalid_object_type"],
)
def test_create_log_object_fails_on_invalid_time(time_input: Any):
    """Test that `time` fails validation on invalid time input."""
    with pytest.raises(ValidationError):
        MozlogDataModel(
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
    log_data = MozlogDataModel(
        errno=0,
        time=datetime_rep,
        path="/",
        method="GET",
    )
    assert log_data.model_dump().get("time") == expected_time


def test_suggest_log_data_model_dumps_flat():
    """Ensure `SuggestLogDataModel` serializes to a flat dict despite being composed
    of `mozlog` and `request_params` submodels, with `time` as an ISO string.
    """
    log_data = SuggestLogDataModel(
        sensitive=True,
        mozlog=MozlogDataModel(
            errno=0,
            time=datetime(2022, 12, 18, hour=15, minute=58, second=41, tzinfo=timezone.utc),
            path="/api/v1/suggest",
            method="GET",
        ),
        request_params=SuggestRequestParams(
            query="nope",
            code=200,
            rid="1b11844c52b34c33a6ad54b7bc2eb7c7",
            session_id="deadbeef-0000-1111-2222-333344445555",
            sequence_no=0,
            client_variants="foo,bar",
            requested_providers="pro,vider",
            country="US",
            region="WA",
            city="Milton",
            dma=819,
            browser="Firefox(103.0)",
            os_family="macos",
            form_factor="desktop",
        ),
    )

    assert log_data.model_dump() == {
        "sensitive": True,
        "errno": 0,
        "time": "2022-12-18T15:58:41+00:00",
        "path": "/api/v1/suggest",
        "method": "GET",
        "query": "nope",
        "code": 200,
        "rid": "1b11844c52b34c33a6ad54b7bc2eb7c7",
        "session_id": "deadbeef-0000-1111-2222-333344445555",
        "sequence_no": 0,
        "client_variants": "foo,bar",
        "requested_providers": "pro,vider",
        "country": "US",
        "region": "WA",
        "city": "Milton",
        "dma": 819,
        "browser": "Firefox(103.0)",
        "os_family": "macos",
        "form_factor": "desktop",
    }


def _request_params(**overrides: Any) -> SuggestRequestParams:
    """Build a minimal `SuggestRequestParams`, applying any field overrides."""
    fields: dict[str, Any] = {
        "query": "nope",
        "code": 200,
        "rid": "1b11844c52b34c33a6ad54b7bc2eb7c7",
        "client_variants": "",
        "requested_providers": "",
        "browser": "Firefox(103.0)",
        "os_family": "macos",
        "form_factor": "desktop",
    }
    return SuggestRequestParams(**(fields | overrides))


def test_suggest_log_data_model_omits_submitted_at():
    """Ensure `submitted_at` never reaches the `web.suggest.request` record.

    The field rides along on `SuggestRequestParams` for the search term submission path,
    so this record's fixed downstream schema is kept intact by an explicit exclusion.
    """
    log_data = SuggestLogDataModel(
        sensitive=True,
        mozlog=MozlogDataModel(
            errno=0,
            time=datetime(2022, 12, 18, hour=15, minute=58, second=41, tzinfo=timezone.utc),
            path="/api/v1/suggest",
            method="GET",
        ),
        request_params=_request_params(submitted_at=datetime(2022, 12, 18, tzinfo=timezone.utc)),
    )

    assert "submitted_at" not in log_data.model_dump()


@pytest.mark.parametrize(
    ("submitted_at", "expected"),
    [
        (
            datetime(2022, 12, 18, hour=15, minute=58, second=41, tzinfo=timezone.utc),
            "2022-12-18T15:58:41+00:00",
        ),
        (
            datetime(
                2022,
                12,
                18,
                hour=7,
                minute=58,
                second=41,
                tzinfo=timezone(timedelta(hours=-8)),
            ),
            "2022-12-18T15:58:41+00:00",
        ),
        (datetime(2022, 12, 18, hour=15, minute=58, second=41), "2022-12-18T15:58:41+00:00"),
        (None, None),
    ],
    ids=["utc", "other_offset_converted", "naive_read_as_utc", "unset"],
)
def test_submitted_at_serializes_as_utc_iso(submitted_at: datetime | None, expected: str | None):
    """Ensure `submitted_at` is dumped as a UTC ISO string BigQuery reads as a TIMESTAMP.

    A str is required, not just preferred: the submission is posted as
    `model_dump()` via httpx, whose encoder rejects a raw datetime, and the mozlog
    formatter would write one out as its `repr`.
    """
    params = _request_params(submitted_at=submitted_at)

    assert params.model_dump()["submitted_at"] == expected
    assert json.loads(params.model_dump_json())["submitted_at"] == expected


def test_sanitized_search_term_log_timestamp_serializes_as_utc_iso():
    """Ensure the log model's `timestamp` gets the same UTC ISO treatment."""
    log = SanitizedSearchTermLog(
        query="nope",
        request_id="1b11844c52b34c33a6ad54b7bc2eb7c7",
        timestamp=datetime(2022, 12, 18, hour=15, minute=58, second=41, tzinfo=timezone.utc),
    )

    assert log.model_dump()["timestamp"] == "2022-12-18T15:58:41+00:00"


def test_submitted_at_round_trips_through_json():
    """Ensure the timestamp survives the wire between Merino and merino-fleece.

    Dumped as a UTC ISO string, re-validated as an aware datetime of the same instant.
    """
    submitted_at = datetime(2022, 12, 18, hour=15, minute=58, second=41, tzinfo=UTC)

    restored = SuggestRequestParams.model_validate_json(
        _request_params(submitted_at=submitted_at).model_dump_json()
    )

    assert restored.submitted_at == submitted_at
