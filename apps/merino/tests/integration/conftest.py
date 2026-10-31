"""Module for test configurations for the integration test directory."""

import asyncio
import os
import time
import threading
import requests
import pytest
import pytest_asyncio

from testcontainers.community.elasticsearch import ElasticSearchContainer
from testcontainers.core.network import Network
from elasticsearch import AsyncElasticsearch

ES_IMAGE = os.environ.get("ES_IMAGE", "merino-elasticsearch:local")

ES_PROP = {
    "container": None,
    "base_url": None,
    "started": threading.Event(),
    "done": threading.Event(),
    "error": None,
    "should_start": False,
    # A second container from the same image, following the first via cross-cluster
    # replication (CCR). Only started for CCR_TESTS.
    "with_follower": False,
    "network": None,
    "follower": None,
    "follower_url": None,
    "follower_done": threading.Event(),
    "follower_error": None,
}

# Test modules that need the Elasticsearch container.
ES_TESTS = ("test_sportsdata", "test_elastic_adapter", "test_indexer_ccr")
# Test modules that also need the CCR follower cluster.
CCR_TESTS = ("test_indexer_ccr",)

# Network alias the follower uses to reach the leader's transport port.
LEADER_ALIAS = "es-leader"


def pytest_collection_modifyitems(session, config, items):
    """Move Elasticsearch tests to the end, giving the container time to start."""
    es_tests = []
    other_tests = []
    for item in items:
        if any(name in item.nodeid for name in ES_TESTS):
            es_tests.append(item)
        else:
            other_tests.append(item)
    ES_PROP["should_start"] = len(es_tests) > 0
    ES_PROP["with_follower"] = any(name in item.nodeid for item in es_tests for name in CCR_TESTS)
    items[:] = other_tests + es_tests


def _es_container(cluster_name: str, alias: str | None = None) -> ElasticSearchContainer:
    """Return an unstarted ES container, joined to the CCR network when there is one."""
    container = ElasticSearchContainer(ES_IMAGE)
    container.with_env("discovery.type", "single-node")
    container.with_env("cluster.name", cluster_name)
    container.with_env("ES_JAVA_OPTS", "-Xms256m -Xmx256m")
    # Prevent local shards from entering into a read-only state due to high disk usage
    container.with_env("cluster.routing.allocation.disk.threshold_enabled", "false")
    network = ES_PROP["network"]
    if network is not None:
        container.with_network(network)
        if alias:
            container.with_network_aliases(alias)
        # testcontainers binds transport to loopback; the follower needs to reach it.
        # Single-node discovery keeps the production bootstrap checks off regardless.
        container.with_env("transport.host", "0.0.0.0")
        # CCR is a Platinum feature, available under the trial license.
        container.with_env("xpack.license.self_generated.type", "trial")
    return container


def _wait_for_green(base_url: str, timeout: float) -> bool:
    """Return whether the cluster at base_url turns green within timeout seconds."""
    time_to_give_up = time.time() + timeout
    health_url = f"{base_url}/_cluster/health?wait_for_status=green&timeout=1s"
    while time.time() < time_to_give_up:
        try:
            r = requests.get(health_url, timeout=2)
            if r.status_code == 200 and r.json().get("status") == "green":
                return True
        except requests.RequestException:
            pass
        time.sleep(0.5)
    return False


def _start_follower_in_thread(timeout=120):
    """Start the CCR follower container and record its status in ES_PROP."""
    try:
        container = _es_container("follower-cluster")
        container.start()
        ES_PROP["follower"] = container
        base_url = f"http://{container.get_container_host_ip()}:{container.get_exposed_port(9200)}"
        ES_PROP["follower_url"] = base_url
        if not _wait_for_green(base_url, timeout):
            ES_PROP["follower_error"] = RuntimeError("Follower status did not turn green")
    except Exception as e:
        ES_PROP["follower_error"] = e
    finally:
        ES_PROP["follower_done"].set()


def _start_container_in_thread(timeout=120):
    """Start container in thread and update container status with ES_PROP."""
    try:
        container = _es_container("leader-cluster", alias=LEADER_ALIAS)
        container.start()

        host = container.get_container_host_ip()
        port = container.get_exposed_port(9200)
        base_url = f"http://{host}:{port}"

        ES_PROP["container"] = container
        ES_PROP["base_url"] = base_url

        ES_PROP["started"].set()

        # time to give up to wait for green status (2mins from now)
        if _wait_for_green(base_url, timeout):
            ES_PROP["done"].set()
            return

        ES_PROP["error"] = RuntimeError("Elasticsearch status did not turn green")
        ES_PROP["done"].set()

    except Exception as e:
        ES_PROP["error"] = e
        ES_PROP["done"].set()


@pytest.fixture(scope="session", autouse=True)
def start_es_background():
    """Start the ES container on a background thread at session start."""
    if not ES_PROP["should_start"]:
        yield
        return

    if ES_PROP["with_follower"]:
        ES_PROP["network"] = Network().create()
        threading.Thread(target=_start_follower_in_thread, daemon=True).start()

    t = threading.Thread(target=_start_container_in_thread, daemon=True)
    t.start()

    yield

    for key in ("follower", "container"):
        container = ES_PROP.get(key)
        if container:
            container.stop()
    if ES_PROP["network"] is not None:
        ES_PROP["network"].remove()


@pytest.fixture
def es_base_url():
    """Return base_url if container.start() has been called"""
    ES_PROP["started"].wait(timeout=10)
    if ES_PROP.get("error") and not ES_PROP.get("base_url"):
        raise ES_PROP["error"]
    return ES_PROP.get("base_url")


@pytest.fixture
def es_url():
    """Wait for the ES cluster to be green and return its URL, for synchronous tests."""
    if not ES_PROP["done"].wait(timeout=130):
        raise RuntimeError("Elasticsearch did not start in time")
    if ES_PROP.get("error"):
        raise ES_PROP["error"]
    return ES_PROP["base_url"]


def _wait_until(check, message: str, timeout: float = 30) -> None:
    """Poll check until it returns something truthy, raising message on timeout."""
    deadline = time.time() + timeout
    while not check():
        if time.time() >= deadline:
            raise RuntimeError(message)
        time.sleep(0.5)


def _put(url: str, json: dict) -> None:
    """PUT json to url, raising with Elasticsearch's explanation on failure."""
    response = requests.put(url, json=json, timeout=10)
    if not response.ok:
        raise RuntimeError(f"PUT {url} failed ({response.status_code}): {response.text}")


@pytest.fixture(scope="session")
def ccr_clusters() -> tuple[str, str]:
    """Wait for both clusters and connect the follower to the leader via auto-follow.

    Return the (leader, follower) URLs. The auto-follow pattern mirrors the one CCR
    deployments need for the wikipedia indexer: it follows `*wiki-*` indices but
    excludes the indexer's `temp-*` build indices.
    """
    for done, error in (("done", "error"), ("follower_done", "follower_error")):
        if not ES_PROP[done].wait(timeout=130):
            raise RuntimeError("Elasticsearch clusters did not start in time")
        if ES_PROP.get(error):
            raise ES_PROP[error]
    leader, follower = ES_PROP["base_url"], ES_PROP["follower_url"]

    # The trial license is installed a few seconds after the cluster turns green, and
    # CCR refuses to start until both clusters have one.
    for url in (leader, follower):
        _wait_until(
            lambda url=url: requests.get(f"{url}/_license", timeout=5).json().get("license"),
            f"No license on {url}",
        )

    _put(
        f"{follower}/_cluster/settings",
        json={"persistent": {"cluster.remote.leader.seeds": [f"{LEADER_ALIAS}:9300"]}},
    )
    # The remote connection, over which the leader's license is checked, is opened
    # asynchronously.
    _wait_until(
        lambda: requests.get(f"{follower}/_remote/info", timeout=5).json()["leader"]["connected"],
        "Follower did not connect to the leader cluster",
    )
    _put(
        f"{follower}/_ccr/auto_follow/wikipedia",
        json={
            "remote_cluster": "leader",
            "leader_index_patterns": ["*wiki-*"],
            "leader_index_exclusion_patterns": ["temp-*"],
            "follow_index_pattern": "{{leader_index}}",
            # Pick up leader metadata changes such as aliases promptly (default 1m).
            "read_poll_timeout": "1s",
        },
    )
    return leader, follower


@pytest_asyncio.fixture
async def es_ready():
    """Async fixture that waits for the ES cluster to be green or raises startup error."""
    await asyncio_wait_for_thread_event(ES_PROP["started"], timeout=10)
    if ES_PROP.get("error") and not ES_PROP.get("base_url"):
        raise ES_PROP["error"]

    await asyncio_wait_for_thread_event(ES_PROP["done"], timeout=120)

    if ES_PROP.get("error"):
        raise ES_PROP["error"]

    base_url = ES_PROP.get("base_url")
    if not base_url:
        raise RuntimeError("Elasticsearch did not start correctly")
    return base_url


@pytest_asyncio.fixture
async def es_client(es_ready):
    """Elasticsearch client fixture."""
    client = AsyncElasticsearch(hosts=[es_ready])
    try:
        yield client
    finally:
        await client.close()


def asyncio_wait_for_thread_event(evt: threading.Event, timeout: float):
    """Return coroutine that resolves when evt.wait() returns."""
    return asyncio.wait_for(asyncio.to_thread(evt.wait, timeout), timeout=timeout)
