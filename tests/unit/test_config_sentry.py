# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the config_sentry.py module."""
import logging

from pytest import LogCaptureFixture

from merino.config_sentry import strip_sensitive_data
from tests.types import FilterCaplogFixture

mock_sentry_hint: dict[str, list] = {"exc_info": [RuntimeError, RuntimeError(), None]}

mock_sentry_event_data: dict = {
    "request": {
        "method": "GET",
        "url": "http://127.0.0.1:8000/api/v1/suggest",
        "query_string": "query_str_foo",
    },
    "exception": {
        "values": [
            {
                "stacktrace": {
                    "frames": [
                        {
                            "filename": "merino/web/api_v1.py",
                            "module": "merino.web.api_v1",
                            "vars": {
                                "request": {
                                    "type": "'http'",
                                    "method": "'GET'",
                                    "path": "'/api/v1/suggest'",
                                },
                                "q": "vars_foo",
                                "providers": "'top_picks,adm'",
                                "client_variants": "None",
                            },
                        },
                        {
                            "filename": "merino/web/api_v1.py",
                            "module": "merino.web.api_v1",
                            "vars": {
                                "values": {
                                    "request": {
                                        "type": "'http'",
                                        "method": "'GET'",
                                        "path": "'/api/v1/suggest'",
                                    },
                                    "q": "vars_values_foo",
                                    "providers": "'top_picks,adm'",
                                    "client_variants": "None",
                                }
                            },
                        },
                        {
                            "filename": "merino/providers/top_picks/provider.py",
                            "function": "query",
                            "context_line": "raise BackendError()",
                            "vars": {
                                "self": "<merino.providers.top_picks.provider>",
                                "srequest": "SuggestionRequest(query='foobar')",
                                "qlen": "6",
                                "query": "foobar",
                                "ids": "None",
                            },
                        },
                        {
                            "filename": "fastapi/routing.py",
                            "function": "app",
                            "module": "fastapi.routing",
                            "lineno": 227,
                            "vars": {
                                "request": {
                                    "type": "'http'",
                                },
                                "body": "None",
                                "solved_result": [
                                    {
                                        "q": "foobar",
                                        "providers": "'top_picks,adm'",
                                        "client_variants": "None",
                                        "request": {
                                            "method": "'GET'",
                                            "path": "'/api/v1/suggest'",
                                        },
                                    },
                                ],
                                "values": {
                                    "sources": [
                                        {
                                            "accuweather": "<merino.providers.weather.provider>",
                                            "adm": "<merino.providers.adm.provider.",
                                            "top_picks": "<merino.providers.top_picks.provider>",
                                            "wikipedia": "<merino.providers.wikipedia.provider>",
                                        },
                                    ],
                                    "q": "'foobar'",
                                    "providers": "'top_picks,adm'",
                                    "client_variants": "None",
                                },
                            },
                        },
                    ]
                },
            }
        ]
    },
}


def test_strip_sensitive_data() -> None:
    """Test that strip_sensitive_data will remove sensitive data."""
    sanitized_event = strip_sensitive_data(mock_sentry_event_data, mock_sentry_hint)
    assert sanitized_event["request"].get("query_string") == ""
    assert "exc_info" in mock_sentry_hint
    assert isinstance(mock_sentry_hint["exc_info"][1], RuntimeError)

    assert (
        sanitized_event["exception"]["values"][0]["stacktrace"]["frames"][0]["vars"][
            "q"
        ]
        == ""
    )
    assert (
        sanitized_event["exception"]["values"][0]["stacktrace"]["frames"][1]["vars"][
            "values"
        ]["q"]
        == ""
    )
    assert (
        sanitized_event["exception"]["values"][0]["stacktrace"]["frames"][2]["vars"][
            "srequest"
        ]
        == ""
    )

    assert (
        sanitized_event["exception"]["values"][0]["stacktrace"]["frames"][3]["vars"][
            "solved_result"
        ][0]["q"]
        == ""
    )


def test_strip_sensitive_data_lookup_error(
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
) -> None:
    """Test that KeyError or IndexError message is emitted through logger when invalid key
    or index is detected.
    """
    caplog.set_level(logging.WARNING)
    strip_sensitive_data(
        event={"bad_request": {}, "exception": {"invalid_values": [{}]}},
        hint=mock_sentry_hint,
    )

    records = filter_caplog(caplog.records, "merino.config_sentry")
    assert (
        records[0].__dict__["msg"]
        == "Encountered KeyError or IndexError for value 'values' while filtering Sentry data."
    )
