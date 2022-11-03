"""Unit tests for the metrics client."""

import aiodogstatsd
import pytest
from pytest_mock import MockerFixture

from merino.featureflags import FeatureFlags
from merino.metrics import Client


@pytest.fixture(name="statsd_mock")
def fixture_statsd_mock(mocker: MockerFixture):
    """Return mock for the StatsD client."""
    return mocker.MagicMock(spec_set=aiodogstatsd.Client)


@pytest.fixture(name="metrics_client")
def fixture_metrics_client(statsd_mock):
    """Return a metrics client."""
    return Client(
        statsd_client=statsd_mock,
        feature_flags=FeatureFlags(),
    )


def test_unsupported_method(metrics_client: Client, statsd_mock):
    """Test that the metrics client raises an error for unsupported methods."""

    want = "attribute 'hello_world' is not supported by metrics.Client class"

    with pytest.raises(AttributeError) as exc_info:
        metrics_client.hello_world(123, "abc")

    # Verify that the exception message is what we expect
    assert str(exc_info.value) == want

    # Verify that the metrics client isn't calling the StatsD client
    statsd_mock.increment.assert_not_called()
    statsd_mock.timeit_task.assert_not_called()
    statsd_mock.timeit.assert_not_called()
