"""Unit tests for the sanitization worker entrypoint."""

import asyncio

import pytest
from pytest_mock import MockerFixture

from merino_fleece.sanitize.worker import main


@pytest.mark.asyncio
async def test_main_wires_dependencies_around_the_pull(mocker: MockerFixture) -> None:
    """The sanitization dependencies come up before the pull and go down after it returns.

    This pins the teardown order the app lifespan also relies on: the pull drains its
    in-flight callbacks before `start()` returns, and those batches still consult the
    exempts and offload NER to the thread pool, so both must outlive it.
    """
    order: list[str] = []
    mocker.patch.object(main, "configure_logging")
    mocker.patch.object(main, "configure_sentry")
    for name in ("init_detector", "init_executor", "shutdown_executor", "shutdown_detector"):
        mocker.patch.object(main, name, side_effect=lambda name=name: order.append(name))

    async def exempts_up() -> None:
        order.append("exempts_up")

    async def exempts_down() -> None:
        order.append("exempts_down")

    mocker.patch.object(main.exempts, "initialize", exempts_up)
    mocker.patch.object(main.exempts, "shutdown", exempts_down)

    worker_cls = mocker.patch.object(main, "FleeceQueueWorker")
    worker_cls.return_value.start.side_effect = lambda: order.append("streaming_pull")

    await main.main()

    assert order == [
        "init_detector",
        "init_executor",
        "exempts_up",
        "streaming_pull",
        "exempts_down",
        "shutdown_executor",
        "shutdown_detector",
    ]
    # The worker must sanitize on the loop that owns those dependencies.
    assert worker_cls.call_args.kwargs["loop"] is asyncio.get_running_loop()


@pytest.mark.asyncio
async def test_main_tears_down_after_a_failed_pull(mocker: MockerFixture) -> None:
    """A pull that raises still releases the detector, thread pool, and exempts."""
    mocker.patch.object(main, "configure_logging")
    mocker.patch.object(main, "configure_sentry")
    mocker.patch.object(main, "init_detector")
    mocker.patch.object(main, "init_executor")
    shutdown_executor = mocker.patch.object(main, "shutdown_executor")
    shutdown_detector = mocker.patch.object(main, "shutdown_detector")
    exempts_shutdown = mocker.patch.object(main.exempts, "shutdown")
    mocker.patch.object(main.exempts, "initialize")
    worker_cls = mocker.patch.object(main, "FleeceQueueWorker")
    worker_cls.return_value.start.side_effect = RuntimeError("subscription is gone")

    with pytest.raises(RuntimeError, match="subscription is gone"):
        await main.main()

    exempts_shutdown.assert_awaited_once_with()
    shutdown_executor.assert_called_once_with()
    shutdown_detector.assert_called_once_with()
