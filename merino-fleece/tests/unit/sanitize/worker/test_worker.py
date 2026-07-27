"""Unit tests for merino_fleece.sanitize.worker.worker."""

from typing import Any
from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture

from merino_common.models.suggest_logging import SuggestRequestParams, SearchTermsSubmission

from merino_fleece.sanitize.models import SanitizedSuggestRequest
from merino_fleece.sanitize.worker.worker import FleeceQueueWorker, callback


def _log_entry(**overrides: Any) -> SuggestRequestParams:
    """Build a valid SuggestRequestParams, applying any field overrides."""
    fields: dict[str, Any] = {
        "query": "how to use fleece in firefox",
        "code": 200,
        "rid": "1b11844c52b34c33a6ad54b7bc2eb7c7",
        "client_variants": "",
        "requested_providers": "",
        "browser": "Firefox(103.0)",
        "os_family": "macos",
        "form_factor": "desktop",
    }
    fields.update(overrides)
    return SuggestRequestParams(**fields)


def test_callback_sanitizes_emits_and_acks(mocker: MockerFixture) -> None:
    """The callback sanitizes each term, emits it, and acks the message."""
    emit = mocker.patch("merino_fleece.sanitize.worker.worker.emit_sanitized_query")
    submission = SearchTermsSubmission(search_terms=[_log_entry(), _log_entry()])
    message = MagicMock()
    message.data = submission.model_dump_json().encode("utf-8")

    callback(message)

    assert emit.call_count == 2
    # Each emitted term is the sanitized request with its query preserved.
    assert all(isinstance(call.args[0], SanitizedSuggestRequest) for call in emit.call_args_list)
    assert all(
        call.args[0].query == "how to use fleece in firefox" for call in emit.call_args_list
    )
    message.ack.assert_called_once_with()


def test_callback_empty_batch_still_acks(mocker: MockerFixture) -> None:
    """A submission with no search terms emits nothing but still acks."""
    emit = mocker.patch("merino_fleece.sanitize.worker.worker.emit_sanitized_query")
    submission = SearchTermsSubmission(search_terms=[])
    message = MagicMock()
    message.data = submission.model_dump_json().encode("utf-8")

    callback(message)

    emit.assert_not_called()
    message.ack.assert_called_once_with()


def test_callback_drops_invalid_message(
    mocker: MockerFixture, caplog: pytest.LogCaptureFixture
) -> None:
    """A message that fails validation is logged, dropped, and still acked."""
    emit = mocker.patch("merino_fleece.sanitize.worker.worker.emit_sanitized_query")
    message = MagicMock()
    message.data = b'{"not": "a valid submission"}'

    with caplog.at_level("ERROR", logger="merino_fleece.sanitize.worker.worker"):
        callback(message)

    emit.assert_not_called()
    assert "Dropping invalid message" in caplog.text
    message.ack.assert_called_once_with()


@pytest.fixture
def subscriber_mock(mocker: MockerFixture) -> MagicMock:
    """Patch the Pub/Sub SubscriberClient and return the client instance mock."""
    client_cls = mocker.patch("merino_fleece.sanitize.worker.worker.pubsub_v1.SubscriberClient")
    instance: MagicMock = client_cls.return_value
    return instance


def test_init_creates_subscriber(subscriber_mock: MagicMock) -> None:
    """The worker stores the subscription name and a subscriber client, not stopping."""
    worker = FleeceQueueWorker("my-subscription")

    assert worker.subscription_name == "my-subscription"
    assert worker.subscriber is subscriber_mock
    assert worker._stopping is False


def test_start_subscribes_and_blocks(subscriber_mock: MagicMock) -> None:
    """start() opens a streaming pull with the worker's subscription and blocks on it."""
    future = subscriber_mock.subscribe.return_value
    worker = FleeceQueueWorker("my-subscription")

    worker.start()

    subscriber_mock.subscribe.assert_called_once_with(
        "my-subscription",
        callback=callback,
        await_callbacks_on_shutdown=True,
    )
    future.result.assert_called_once_with(timeout=None)


def test_stop_cancels_future_and_sets_flag(subscriber_mock: MagicMock) -> None:
    """stop() marks the worker as stopping and cancels the active streaming pull future."""
    future = subscriber_mock.subscribe.return_value
    worker = FleeceQueueWorker("my-subscription")
    worker.start()

    worker.stop()

    assert worker._stopping is True
    future.cancel.assert_called_once_with()


def test_stop_prevents_reconnect_after_error(
    subscriber_mock: MagicMock, mocker: MockerFixture
) -> None:
    """When stop() runs mid-stream, the resulting error does not trigger a reconnect."""
    sleep = mocker.patch("merino_fleece.sanitize.worker.worker.time.sleep")
    worker = FleeceQueueWorker("my-subscription")
    future = subscriber_mock.subscribe.return_value

    def stop_then_raise(timeout: float | None = None) -> None:
        # Simulate stop() being called while result() is blocking on the stream.
        worker.stop()
        raise RuntimeError("stream cancelled")

    future.result.side_effect = stop_then_raise

    worker.start()

    # Stopped intentionally: no delay and no rebuilt client beyond the initial connect.
    sleep.assert_not_called()
    assert subscriber_mock.subscribe.call_count == 1


def test_restarts_after_stream_error(
    subscriber_mock: MagicMock, mocker: MockerFixture, caplog: pytest.LogCaptureFixture
) -> None:
    """A streaming error is logged, the future cancelled, and the stream restarted."""
    sleep = mocker.patch("merino_fleece.sanitize.worker.worker.time.sleep")
    subscriber_mock.closed = True  # restart() only proceeds on a closed client
    future = subscriber_mock.subscribe.return_value
    # First stream dies; the restarted stream blocks then returns cleanly.
    future.result.side_effect = [RuntimeError("stream died"), None]
    worker = FleeceQueueWorker("my-subscription", restart_backoff=5)

    with caplog.at_level("ERROR", logger="merino_fleece.sanitize.worker.worker"):
        worker.start()

    assert "Encountered exception during message streaming" in caplog.text
    future.cancel.assert_called_once_with()
    sleep.assert_called_once_with(5)
    # subscribe: once in __init__, once on restart. result: initial + restarted stream.
    assert subscriber_mock.subscribe.call_count == 2
    assert future.result.call_count == 2


def test_restart_ignored_while_subscriber_open(
    subscriber_mock: MagicMock, caplog: pytest.LogCaptureFixture
) -> None:
    """restart() is a no-op (with a warning) when the subscriber is still open."""
    subscriber_mock.closed = False
    worker = FleeceQueueWorker("my-subscription")
    subscriber_mock.subscribe.reset_mock()

    with caplog.at_level("WARNING", logger="merino_fleece.sanitize.worker.worker"):
        worker.restart()

    subscriber_mock.subscribe.assert_not_called()
    assert "Ignored attempt to restart open subscription" in caplog.text
