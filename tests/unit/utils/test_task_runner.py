import asyncio

import pytest
import pytest_asyncio
from pytest import LogCaptureFixture
from pytest_mock import MockerFixture

from merino.utils.task_runner import gather
from tests.types import FilterCaplogFixture

# The duration of the slow coroutine (500 ms).
SLOW_COROUTINE_DURATION = 0.5


@pytest_asyncio.fixture(name="normal_task")
async def fixture_normal_task() -> asyncio.Task:
    async def normal_op() -> bool:
        return True

    return asyncio.create_task(normal_op(), name="normal-task")


@pytest_asyncio.fixture(name="timedout_task")
async def fixture_timedout_task() -> asyncio.Task:
    async def some_slow_op() -> bool:
        await asyncio.sleep(SLOW_COROUTINE_DURATION)
        return True

    return asyncio.create_task(some_slow_op(), name="timedout-task")


@pytest_asyncio.fixture(name="raised_task")
async def fixture_raised_task() -> asyncio.Task:
    async def will_raise() -> None:
        raise RuntimeError("error")

    return asyncio.create_task(will_raise(), name="raised-task")


@pytest.mark.asyncio
async def test_gather_without_tasks() -> None:
    """Test gather with an empty task list"""
    done_tasks, timedout_tasks = await gather([])

    assert done_tasks == []
    assert timedout_tasks == []


@pytest.mark.asyncio
async def test_gather_tasks_with_timeout(
    normal_task,
    timedout_task,
    raised_task,
    mocker: MockerFixture,
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
) -> None:
    """Test gather with timed out tasks"""
    stub = mocker.stub(name="timeout_callback")

    done_tasks, timedout_tasks = await gather(
        [normal_task, timedout_task, raised_task],
        timeout=SLOW_COROUTINE_DURATION / 2,
        timeout_cb=stub,
    )

    assert len(done_tasks) == 2
    for task in done_tasks:
        match task.get_name():
            case "normal-task":
                assert await task
            case "raised-task":
                with pytest.raises(RuntimeError) as exc_info:
                    await task
                assert str(exc_info.value) == "error"
            case _:
                raise AssertionError(f"Unexpected task: {task.get_name()}")

    assert len(timedout_tasks) == 1
    assert timedout_tasks[0].get_name() == "timedout-task"

    stub.assert_called_once_with([timedout_task])

    # Check logs
    records = filter_caplog(caplog.records, "merino.utils.task_runner")

    assert len(records) == 2
    assert records[0].__dict__["msg"] == "Timeout triggered in the task runner"
    assert (
        records[1].__dict__["msg"]
        == "Cancelling the task: timedout-task due to timeout"
    )


@pytest.mark.asyncio
async def test_gather_tasks_without_timeout(
    normal_task,
    timedout_task,
    raised_task,
    mocker: MockerFixture,
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
) -> None:
    """Test gather without timeout"""
    stub = mocker.stub(name="timeout_callback")

    done_tasks, timedout_tasks = await gather(
        [normal_task, timedout_task, raised_task],
        timeout=None,
        timeout_cb=stub,
    )

    assert len(done_tasks) == 3
    for task in done_tasks:
        match task.get_name():
            case "normal-task" | "timedout-task":
                assert await task
            case "raised-task":
                with pytest.raises(RuntimeError) as exc_info:
                    await task
                assert str(exc_info.value) == "error"
            case _:
                raise AssertionError(f"Unexpected task: {task.get_name()}")

    assert len(timedout_tasks) == 0

    stub.assert_not_called()

    # Check logs
    records = filter_caplog(caplog.records, "merino.utils.task_runner")

    assert len(records) == 0


@pytest.mark.asyncio
async def test_gather_tasks_without_timeout_callback(
    normal_task,
    timedout_task,
    raised_task,
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
) -> None:
    """Test gather without timeout callback"""
    done_tasks, timedout_tasks = await gather(
        [normal_task, timedout_task, raised_task],
        timeout=SLOW_COROUTINE_DURATION / 2,
        timeout_cb=None,
    )

    assert len(done_tasks) == 2
    for task in done_tasks:
        match task.get_name():
            case "normal-task":
                assert await task
            case "raised-task":
                with pytest.raises(RuntimeError) as exc_info:
                    await task
                assert str(exc_info.value) == "error"
            case _:
                raise AssertionError(f"Unexpected task: {task.get_name()}")

    assert len(timedout_tasks) == 1
    assert timedout_tasks[0].get_name() == "timedout-task"

    # Check logs
    records = filter_caplog(caplog.records, "merino.utils.task_runner")

    assert len(records) == 2
    assert records[0].__dict__["msg"] == "Timeout triggered in the task runner"
    assert (
        records[1].__dict__["msg"]
        == "Cancelling the task: timedout-task due to timeout"
    )
