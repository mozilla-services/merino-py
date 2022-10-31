import pytest
from starlette.testclient import TestClient

from merino.main import app


@pytest.fixture(name="client")
def fixture_test_client() -> TestClient:
    """
    Return a FastAPI TestClient instance for use in test methods
    """
    return TestClient(app)
