# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the config_sentry.py module."""

from merino.config_sentry import strip_sensitive_data

mock_sentry_hint: dict[str, list] = {"exc_info": [RuntimeError, RuntimeError(), None]}

mock_sentry_event_data: dict = {
    "request": {
        "method": "GET",
        "url": "http://localhost:8000/api/v1/suggest",
        "query_string": "query_str_foo",
    },
    "exception": {
        "values": [
            {
                "stacktrace": {
                    "frames": [
                        {
                            "request": {
                                "method": "'GET'",
                                "path": "'/api/v1/suggest'",
                            },
                            "solved_result": [
                                {
                                    "sources": [
                                        {
                                            "accuweather": "<merino.providers.weather>",
                                            "adm": "<merino.providers.adm>",
                                            "top_picks": "<merino.providers.top_picks>",
                                            "wikipedia": "<merino.providers.wikipedia>",
                                        },
                                        ["<merino.providers.adm.provider>"],
                                    ],
                                    "q": "solved_foo",
                                    "providers": "'top_picks,adm'",
                                    "client_variants": "None",
                                    "request": {
                                        "method": "'GET'",
                                        "path": "'/api/v1/suggest'",
                                    },
                                },
                            ],
                        },
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
                    ]
                },
            }
        ]
    },
}


def test_strip_sensitive_data() -> None:
    """Test that strip_sensitive_data will remove sensitive data."""
    sentry_event = strip_sensitive_data(mock_sentry_event_data, mock_sentry_hint)
    # Asserts that the 'query_string' key was removed from the dictionary.
    assert sentry_event["request"].get("query_string") == "query_str_foo"
    assert isinstance(mock_sentry_hint["exc_info"][1], RuntimeError)
    assert (
        sentry_event["exception"]["values"][0]["stacktrace"]["frames"][0][
            "solved_result"
        ][0]["q"]
        == "solved_foo"
    )
    assert (
        sentry_event["exception"]["values"][0]["stacktrace"]["frames"][1]["vars"]["q"]
        == "vars_foo"
    )

    assert (
        sentry_event["exception"]["values"][0]["stacktrace"]["frames"][2]["vars"][
            "values"
        ]["q"]
        == "vars_values_foo"
    )
