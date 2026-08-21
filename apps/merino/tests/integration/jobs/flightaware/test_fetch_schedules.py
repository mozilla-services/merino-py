# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Integration tests for fetch_schedules.py module."""

import httpx
import asyncio
import json
from unittest.mock import MagicMock, patch
from merino.jobs.flightaware.fetch_schedules import (
    store_flight_numbers_in_gcs,
    fetch_schedules,
)


def test_fetch_with_mock_transport():
    """Verify fetch_schedules handles a single-page response with one flight."""

    def handler(request):
        return httpx.Response(200, json={"scheduled": [{"ident_iata": "AA123"}], "links": {}})

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, base_url="https://aeroapi.flightaware.com/aeroapi")

    flights, calls = fetch_schedules(client)

    assert "AA123" in flights
    assert calls == 1


def test_fetch_schedules_with_pagination():
    """Verify fetch_schedules follows links.next and collects flights across multiple pages."""
    responses = [
        httpx.Response(
            200,
            json={
                "scheduled": [{"ident_iata": "AA123"}],
                "links": {"next": "/schedules/page2"},
            },
        ),
        httpx.Response(200, json={"scheduled": [{"ident_iata": "UA456"}], "links": {}}),
    ]
    call_count = {"i": 0}

    def handler(request):
        resp = responses[call_count["i"]]
        call_count["i"] += 1
        return resp

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, base_url="https://aeroapi.flightaware.com/aeroapi")

    flights, calls = fetch_schedules(client)

    assert "AA123" in flights
    assert "UA456" in flights
    assert calls == 2


def test_store_flight_numbers_in_gcs_first_upload():
    """Ensure store_flight_numbers_in_gcs uploads all numbers when no existing blob is present."""
    mock_uploader = MagicMock()
    mock_uploader.get_most_recent_file.return_value = None

    with patch(
        "merino.jobs.flightaware.fetch_schedules.GcsUploader",
        return_value=mock_uploader,
    ):
        flight_numbers = {"AA123", "UA456"}
        asyncio.run(store_flight_numbers_in_gcs(flight_numbers))

    uploaded_content = mock_uploader.upload_content.call_args[1]["content"]
    uploaded_list = json.loads(uploaded_content)
    assert sorted(uploaded_list) == ["AA123", "UA456"]


def test_store_flight_numbers_in_gcs_merges_existing():
    """Ensure store_flight_numbers_in_gcs merges new numbers with existing blob contents and dedupes."""
    mock_blob = MagicMock()
    mock_blob.download_as_text.return_value = json.dumps(["AA123", "DL789"])
    mock_uploader = MagicMock()
    mock_uploader.get_most_recent_file.return_value = mock_blob

    with patch(
        "merino.jobs.flightaware.fetch_schedules.GcsUploader",
        return_value=mock_uploader,
    ):
        flight_numbers = {"AA123", "UA456"}  # AA123 is already in the blob
        asyncio.run(store_flight_numbers_in_gcs(flight_numbers))

    uploaded_content = mock_uploader.upload_content.call_args[1]["content"]
    uploaded_list = json.loads(uploaded_content)

    assert "AA123" in uploaded_list
    assert "DL789" in uploaded_list
    assert "UA456" in uploaded_list
    assert len(uploaded_list) == 3


def test_fetch_schedules_handles_links_null():
    """Verify fetch_schedules exits gracefully when 'links' is null in the response."""

    def handler(request):
        return httpx.Response(
            200,
            json={
                "scheduled": [{"ident_iata": "AA123"}],
                "links": None,
            },
        )

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, base_url="https://aeroapi.flightaware.com/aeroapi")

    flights, calls = fetch_schedules(client)

    # It should have collected the flight and stopped
    assert flights == {"AA123"}
    assert calls == 1
