"""Unit tests for the sanitization worker entrypoint."""

import pytest
from pytest_mock import MockerFixture

from merino_fleece.sanitize.worker import main
from merino_fleece.sanitize.worker.worker import SubscriberTuning


@pytest.fixture
def stub_bootstrap(mocker: MockerFixture) -> list[str]:
    """Neutralize the entrypoint's global setup, recording lifecycle calls in order."""
    order: list[str] = []
    mocker.patch.object(main, "configure_logging")
    mocker.patch.object(main, "configure_sentry")
    mocker.patch.object(main, "SubscriberClient")
    for name in ("init_detector", "init_executor", "shutdown_executor", "shutdown_detector"):
        mocker.patch.object(main, name, side_effect=lambda name=name: order.append(name))

    async def up() -> None:
        order.append("exempts_up")

    async def down() -> None:
        order.append("exempts_down")

    mocker.patch.object(main.exempts, "initialize", up)
    mocker.patch.object(main.exempts, "shutdown", down)
    return order


@pytest.mark.asyncio
async def test_main_wires_dependencies_around_the_subscriber(
    stub_bootstrap: list[str], mocker: MockerFixture
) -> None:
    """Dependencies come up before the subscriber and are released after it returns.

    This pins the teardown order: cancelling the subscriber drains the messages already in
    flight, and those still consult the exempts and offload NER to the thread pool, so both
    must outlive it.
    """

    async def subscribe(*args: object, **kwargs: object) -> None:
        stub_bootstrap.append("subscribing")

    mocker.patch.object(main, "subscribe", subscribe)

    await main.main()

    assert stub_bootstrap == [
        "init_detector",
        "init_executor",
        "exempts_up",
        "subscribing",
        "exempts_down",
        "shutdown_executor",
        "shutdown_detector",
    ]


@pytest.mark.asyncio
async def test_main_tears_down_after_a_subscriber_failure(
    stub_bootstrap: list[str], mocker: MockerFixture
) -> None:
    """A subscriber that dies propagates, but only after releasing every dependency.

    The exception reaching the caller is what exits the process non-zero so Kubernetes
    recycles the pod rather than leaving it idling in a half-broken state.
    """

    async def subscribe(*args: object, **kwargs: object) -> None:
        raise RuntimeError("a subscriber worker shut down unexpectedly")

    mocker.patch.object(main, "subscribe", subscribe)

    with pytest.raises(RuntimeError, match="shut down unexpectedly"):
        await main.main()

    assert stub_bootstrap[-3:] == ["exempts_down", "shutdown_executor", "shutdown_detector"]


@pytest.mark.asyncio
async def test_main_sizes_the_subscriber_from_the_ack_deadline(
    stub_bootstrap: list[str], monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture
) -> None:
    """Every subscriber limit comes from `SubscriberTuning`, and only one producer is used.

    A second producer would get its own queue and consumer, doubling both concurrency and
    prefetch and invalidating the budget those numbers were derived against.
    """
    monkeypatch.setitem(main.settings.pii, "executor_max_workers", 4)
    monkeypatch.setitem(main.settings.pubsub, "ack_deadline_sec", 30.0)
    subscribe = mocker.patch.object(main, "subscribe")

    await main.main()

    kwargs = subscribe.call_args.kwargs
    expected = SubscriberTuning.derive(ack_deadline_s=30.0, ner_workers=4)
    assert kwargs["num_producers"] == 1
    assert kwargs["num_tasks_per_consumer"] == expected.concurrency
    assert kwargs["max_messages_per_producer"] == expected.max_messages_per_pull
    assert kwargs["ack_deadline"] == 30.0
