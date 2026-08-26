"""Unit tests for merino_fleece.sanitize.worker.worker."""

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from gcloud.aio.pubsub import SubscriberMessage
from pytest_mock import MockerFixture

from merino_common.models.suggest_logging import SearchTermsSubmission, SuggestRequestParams

from merino_fleece.sanitize.worker.worker import (
    SubscriberTuning,
    SLOW_BATCH_S,
    build_handler,
    heartbeat,
)

QUERY = "how to use fleece in firefox"

PUBLISH_TIME = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)


def _log_entry(**overrides: Any) -> SuggestRequestParams:
    """Build a valid SuggestRequestParams, applying any field overrides."""
    fields: dict[str, Any] = {
        "query": QUERY,
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


def _message(*terms: SuggestRequestParams) -> SubscriberMessage:
    """Build a SubscriberMessage carrying a submission of the given terms."""
    data = SearchTermsSubmission(search_terms=list(terms)).model_dump_json().encode("utf-8")
    return SubscriberMessage(
        ack_id="ack-id",
        message_id="message-id",
        publish_time=PUBLISH_TIME,
        data=data,
        attributes={},
    )


def _raw_message(data: bytes) -> SubscriberMessage:
    """Build a SubscriberMessage carrying arbitrary bytes."""
    return SubscriberMessage(
        ack_id="ack-id",
        message_id="message-id",
        publish_time=PUBLISH_TIME,
        data=data,
        attributes={},
    )


@pytest.mark.asyncio
async def test_handler_sanitizes_the_whole_submission(mocker: MockerFixture) -> None:
    """Every term in a message is sanitized as one batch, and the handler returns.

    Returning is what acks the message under `subscribe()`'s contract, so a clean return
    means the terms are classified and logged -- not merely received.
    """
    batches: list[list[SuggestRequestParams]] = []

    async def record(batch: list[SuggestRequestParams]) -> None:
        batches.append(batch)

    mocker.patch("merino_fleece.sanitize.worker.worker.sanitize_batch", record)

    await build_handler(30.0)(_message(_log_entry(), _log_entry()))

    assert [[term.query for term in batch] for batch in batches] == [[QUERY, QUERY]]


@pytest.mark.asyncio
async def test_handler_acks_invalid_message(
    mocker: MockerFixture, caplog: pytest.LogCaptureFixture
) -> None:
    """A message that fails validation is logged and returns, so it is acked not retried."""
    sanitize = mocker.patch("merino_fleece.sanitize.worker.worker.sanitize_batch")

    with caplog.at_level("ERROR", logger="merino_fleece.sanitize.worker.worker"):
        await build_handler(30.0)(_raw_message(b'{"not": "a valid submission"}'))

    sanitize.assert_not_called()
    assert "Dropping invalid message" in caplog.text


@pytest.mark.asyncio
async def test_handler_propagates_sanitization_failure(mocker: MockerFixture) -> None:
    """A failed batch raises, which is how `subscribe()` is told to nack the message."""

    async def boom(batch: list[SuggestRequestParams]) -> None:
        raise RuntimeError("NER blew up")

    mocker.patch("merino_fleece.sanitize.worker.worker.sanitize_batch", boom)

    with pytest.raises(RuntimeError, match="NER blew up"):
        await build_handler(30.0)(_message(_log_entry()))


@pytest.mark.asyncio
async def test_handler_cancels_and_raises_on_timeout(
    mocker: MockerFixture, caplog: pytest.LogCaptureFixture
) -> None:
    """A batch that outruns the timeout is cancelled in place and the message nacked."""
    cancelled = asyncio.Event()

    async def hang(batch: list[SuggestRequestParams]) -> None:
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    mocker.patch("merino_fleece.sanitize.worker.worker.sanitize_batch", hang)

    with caplog.at_level("ERROR", logger="merino_fleece.sanitize.worker.worker"):
        with pytest.raises(TimeoutError):
            await build_handler(0.05)(_message(_log_entry()))

    assert "Timed out sanitizing search terms" in caplog.text
    assert cancelled.is_set(), "the sanitization pass must be cancelled, not left running"


@pytest.mark.asyncio
async def test_heartbeat_refreshes_the_file(tmp_path: Path) -> None:
    """Each tick writes a fresh epoch timestamp, creating parent directories on demand."""
    path = tmp_path / "nested" / "heartbeat"

    task = asyncio.create_task(heartbeat(str(path), 0.01))
    await asyncio.sleep(0.05)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)

    assert path.read_text().isdigit()
    assert not (tmp_path / "nested" / "heartbeat.tmp").exists()  # no leftover tmp file


@pytest.mark.asyncio
async def test_heartbeat_survives_write_failure(
    mocker: MockerFixture, caplog: pytest.LogCaptureFixture
) -> None:
    """A failed write is logged and the task keeps ticking rather than dying."""
    write = mocker.patch(
        "merino_fleece.sanitize.worker.worker._write_heartbeat",
        side_effect=OSError("read-only file system"),
    )

    with caplog.at_level("ERROR", logger="merino_fleece.sanitize.worker.worker"):
        task = asyncio.create_task(heartbeat("/heartbeat", 0.01))
        await asyncio.sleep(0.05)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    assert write.call_count > 1, "the first failure must not abort the loop"
    assert "Failed to refresh heartbeat file" in caplog.text


@pytest.mark.parametrize(
    ("ack_deadline_s", "ner_workers"),
    [
        pytest.param(30.0, 1, id="default-pod"),
        pytest.param(30.0, 4, id="four-core-pod"),
        pytest.param(10.0, 2, id="short-deadline"),
        pytest.param(600.0, 8, id="long-deadline"),
    ],
)
def test_tuning_keeps_a_message_inside_the_ack_deadline(
    ack_deadline_s: float, ner_workers: int
) -> None:
    """Worst-case queue wait plus the sanitization ceiling must fit in the ack deadline.

    This is the invariant the whole derivation exists for: `gcloud-aio-pubsub` never
    extends leases, so a message that outlives the deadline is redelivered mid-flight and
    its terms are logged twice.
    """
    tuning = SubscriberTuning.derive(ack_deadline_s=ack_deadline_s, ner_workers=ner_workers)

    batches_per_task = tuning.max_messages_per_pull / tuning.concurrency
    worst_case_s = batches_per_task * SLOW_BATCH_S + tuning.sanitize_timeout_s

    assert worst_case_s < ack_deadline_s, (
        f"a message could take {worst_case_s:.1f}s against a {ack_deadline_s}s deadline"
    )
    # Prefetching less than can be processed at once would idle the NER pool.
    assert tuning.max_messages_per_pull >= tuning.concurrency
    assert tuning.max_messages_per_pull <= 1000, "Pub/Sub caps a pull at 1000 messages"
