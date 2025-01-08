# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the config_sentry.py module."""

import logging
import typing

from pytest import LogCaptureFixture
from sentry_sdk.types import Event

from merino.configs.app_configs.config_sentry import REDACTED_TEXT, strip_sensitive_data
from tests.types import FilterCaplogFixture

mock_sentry_hint: dict[str, list] = {"exc_info": [RuntimeError, RuntimeError(), None]}

mock_sentry_event_data: Event = {
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
                        {
                            "function": "search",
                            "module": "merino.providers.wikipedia.backends.elastic",
                            "filename": "merino/providers/wikipedia/backends/elastic.py",
                            "abs_path": "/app/merino/providers/wikipedia/backends/elastic.py",
                            "lineno": 69,
                            "pre_context": [
                                "                },",
                                "            }",
                                "        }",
                                "",
                                "        try:",
                            ],
                            "context_line": "            res = await self.client.search(",
                            "post_context": [
                                "                index=INDEX_ID,",
                                "                suggest=suggest,",
                                "                timeout=TIMEOUT_MS,",
                                '                source_includes=["title"],',
                                "            )",
                            ],
                            "in_app": True,
                            "vars": {
                                "q": "what?",
                                "self": "<merino.providers.wikipedia.backends."
                                "elastic.ElasticBackend object at 0x7faaebfb0380>",
                                "suggest": {
                                    "suggest-on-title": {
                                        "completion": {
                                            "field": "'suggest'",
                                            "size": "3",
                                        },
                                        "prefix": "'foobar'",
                                    }
                                },
                            },
                        },
                        {
                            "function": "perform_request",
                            "module": "elasticsearch._async.client._base",
                            "filename": "elasticsearch/_async/client/_base.py",
                            "abs_path": "/usr/local/lib/python3.12/site-packages"
                            "/elasticsearch/_async/client/_base.py",
                            "lineno": 285,
                            "pre_context": [
                                "        if params:",
                                '            target = f"{path}?{_quote_query(params)}"',
                                "        else:",
                                "            target = path",
                                "",
                            ],
                            "context_line": "        meta, resp_body"
                            " = await self.transport.perform_request(",
                            "post_context": [
                                "            method,",
                                "            target,",
                                "            headers=request_headers,",
                                "            body=body,",
                                "            request_timeout=self._request_timeout,",
                            ],
                            "in_app": False,
                            "vars": {
                                "body": {
                                    "suggest": {
                                        "suggest-on-title": {
                                            "completion": '{"field":"\'suggest\'","size":"3"}',
                                            "prefix": "'foobar'",
                                        }
                                    },
                                    "timeout": "'5000ms'",
                                },
                                "headers": {
                                    "accept": "'application/json'",
                                    "content-type": "'application/json'",
                                },
                                "method": "'POST'",
                                "mimetype_header_to_compat": "<function BaseClient."
                                "perform_request.<locals>."
                                "mimetype_header_to_compat at 0x7faad33b9760>",
                                "params": {"_source_includes": ["'title'"]},
                                "path": "'/enwiki-v1/_search'",
                                "request_headers": {
                                    "Accept": "'application/vnd.elasticsearch+json;"
                                    " compatible-with=8'",
                                    "Content-Type": "'application/vnd.elasticsearch+json;"
                                    " compatible-with=8'",
                                    "authorization": "[Filtered]",
                                },
                                "self": "<AsyncElasticsearch(["
                                "'https://cb169725a2b843a2891476b0afb67df2.psc.us-west1"
                                ".gcp.cloud.es.io:9243'])>",
                                "target": "'/enwiki-v1/_search?_source_includes=title'",
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
    sanitized_event = typing.cast(
        Event, strip_sensitive_data(mock_sentry_event_data, mock_sentry_hint)
    )
    assert sanitized_event["request"].get("query_string") == REDACTED_TEXT
    assert "exc_info" in mock_sentry_hint
    assert isinstance(mock_sentry_hint["exc_info"][1], RuntimeError)

    assert (
        sanitized_event["exception"]["values"][0]["stacktrace"]["frames"][0]["vars"]["q"]
        == REDACTED_TEXT
    )
    assert (
        sanitized_event["exception"]["values"][0]["stacktrace"]["frames"][1]["vars"]["values"]["q"]
        == REDACTED_TEXT
    )
    assert (
        sanitized_event["exception"]["values"][0]["stacktrace"]["frames"][2]["vars"]["srequest"]
        == REDACTED_TEXT
    )

    assert (
        sanitized_event["exception"]["values"][0]["stacktrace"]["frames"][4]["vars"]["q"]
        == REDACTED_TEXT
    )
    assert (
        sanitized_event["exception"]["values"][0]["stacktrace"]["frames"][4]["vars"]["suggest"]
        == REDACTED_TEXT
    )
    assert (
        sanitized_event["exception"]["values"][0]["stacktrace"]["frames"][5]["vars"]["body"]
        == REDACTED_TEXT
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
        event={"bad_request": {}, "exception": {"invalid_values": [{}]}},  # type: ignore
        hint=mock_sentry_hint,
    )

    records = filter_caplog(caplog.records, "merino.config_sentry")
    assert (
        records[0].__dict__["msg"]
        == "Encountered KeyError or IndexError for value 'values' while filtering Sentry data."
    )
