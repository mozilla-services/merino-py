# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the Pub/Sub backup channel client."""

from collections.abc import Callable

import pytest
from pytest_mock import MockerFixture

from merino.configs import settings
from merino.message_handlers.search_terms.pubsub import PubSubClient, create_publisher_client
from merino_common.models.suggest_logging import SearchTermsSubmission, SuggestRequestParams
from tests.unit.message_handlers.search_terms.conftest import SUBMITTED_AT

Params = Callable[[str], SuggestRequestParams]


def test_create_publisher_client_uses_adc_when_skipping_auth(mocker: MockerFixture) -> None:
    """Test that release envs (skip_gcp_client_auth) build the client with ADC (no creds)."""
    publisher = mocker.patch("merino.message_handlers.search_terms.pubsub.PublisherClient")
    mocker.patch.object(settings.runtime, "skip_gcp_client_auth", True)

    create_publisher_client()

    publisher.assert_called_once_with()


def test_create_publisher_client_uses_anonymous_creds_otherwise(mocker: MockerFixture) -> None:
    """Test that dev/testing envs build the client with anonymous credentials."""
    publisher = mocker.patch("merino.message_handlers.search_terms.pubsub.PublisherClient")
    mocker.patch.object(settings.runtime, "skip_gcp_client_auth", False)

    create_publisher_client()

    assert "credentials" in publisher.call_args.kwargs


@pytest.mark.asyncio
async def test_publish_sends_sanitized_submission(mocker: MockerFixture, params: Params) -> None:
    """Test that publish sends the batch as a SearchTermsSubmission JSON payload."""
    publisher = mocker.MagicMock()
    publisher.publish.return_value.result.return_value = "message-id"

    client = PubSubClient(publisher=publisher, topic="projects/p/topics/t")
    await client.publish([params("apple"), params("orange")])

    publisher.publish.assert_called_once()
    topic, data = publisher.publish.call_args.args
    assert topic == "projects/p/topics/t"
    submission = SearchTermsSubmission.model_validate_json(data)
    assert [term.query for term in submission.search_terms] == ["apple", "orange"]
    # The backup channel must carry the submission timestamp too, since a replayed
    # message is sanitized and logged long after it was published.
    assert [term.submitted_at for term in submission.search_terms] == [SUBMITTED_AT, SUBMITTED_AT]


@pytest.mark.asyncio
async def test_publish_filters_email_and_numeric(mocker: MockerFixture, params: Params) -> None:
    """Test that email and numeric queries are dropped before publishing."""
    publisher = mocker.MagicMock()
    publisher.publish.return_value.result.return_value = "message-id"

    client = PubSubClient(publisher=publisher, topic="projects/p/topics/t")
    await client.publish([params("foo@bar.com"), params("flight 123"), params("apple")])

    topic, data = publisher.publish.call_args.args
    submission = SearchTermsSubmission.model_validate_json(data)
    assert [term.query for term in submission.search_terms] == ["apple"]


@pytest.mark.asyncio
async def test_publish_skips_when_all_filtered(mocker: MockerFixture, params: Params) -> None:
    """Test that nothing is published when every term is filtered out."""
    publisher = mocker.MagicMock()

    client = PubSubClient(publisher=publisher, topic="projects/p/topics/t")
    await client.publish([params("a@b.com"), params("999")])

    publisher.publish.assert_not_called()


@pytest.mark.asyncio
async def test_publish_raises_on_publish_error(mocker: MockerFixture, params: Params) -> None:
    """Test that a publish failure propagates so the caller records the data-loss outcome."""
    publisher = mocker.MagicMock()
    publisher.publish.return_value.result.side_effect = RuntimeError("pubsub down")

    client = PubSubClient(publisher=publisher, topic="projects/p/topics/t")
    with pytest.raises(RuntimeError, match="pubsub down"):
        await client.publish([params("apple")])


def test_close_closes_transport(mocker: MockerFixture) -> None:
    """Test that closing the client closes the publisher transport."""
    publisher = mocker.MagicMock()

    client = PubSubClient(publisher=publisher, topic="projects/p/topics/t")
    client.close()

    publisher.transport.close.assert_called_once()
