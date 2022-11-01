"""Unit tests for the metrics client."""

import pytest
from aiodogstatsd import Client as StatsDClient

from merino.featureflags import FeatureFlags
from merino.metrics import Client


@pytest.fixture(name="statsd_mock")
def fixture_statsd_mock(mocker):
    """Return mock for the StatsD client."""
    return mocker.MagicMock(spec_set=StatsDClient)


@pytest.fixture(name="client")
def fixture_client(statsd_mock):
    """Return a metrics client."""
    return Client(
        statsd_client=statsd_mock,
        feature_flags=FeatureFlags(),
    )


def test_unsupported_method(client, statsd_mock):
    """Test that the metrics client raises an error for unsupported methods."""

    want = "attribute 'hello_world' is not supported by metrics.Client class"

    with pytest.raises(AttributeError) as exc_info:
        client.hello_world(123, "abc")

    # Verify that the exception message is what we expect
    assert str(exc_info.value) == want

    # Verify that the metrics client isn't calling the StatsD client
    statsd_mock.increment.assert_not_called()
