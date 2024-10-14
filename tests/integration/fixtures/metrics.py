"""Module dedicated to Pytest fixtures for our StatsD metrics client."""

import pytest
from aiodogstatsd import Client


@pytest.fixture
def metrics_client(mocker):
    """Return a mock aiodogstatsd Client instance."""
    metrics_client = mocker.Mock(spec=Client)
    metrics_client.timeit.return_value.__enter__ = lambda *args: None
    metrics_client.timeit.return_value.__exit__ = lambda *args: None
    return metrics_client
