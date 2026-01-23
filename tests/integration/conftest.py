# """Module for test configurations for the integration test directory."""
#
# import asyncio
# import os
# import time
# import threading
# import requests
# import pytest
# import pytest_asyncio
#
# # need this env before importing test containers
# # ryuk is a container that helps with clean up, but since we explicitly stop test containers, it should be okay.
# os.environ["TESTCONTAINERS_RYUK_DISABLED"] = "true"
# from testcontainers.elasticsearch import ElasticSearchContainer  # noqa
# from elasticsearch import AsyncElasticsearch  # noqa
#
#
# Temporary skip for further investigation
collect_ignore = ["providers/suggest/sports/backends/test_sportsdata.py"]
#
# ES_PROP = {
#     "container": None,
#     "base_url": None,
#     "started": threading.Event(),
#     "done": threading.Event(),
#     "error": None,
# }
#
#
# def _start_container_in_thread(timeout=120):
#     """Start container in thread and update container status with ES_PROP."""
#     try:
#         container = ElasticSearchContainer("docker.elastic.co/elasticsearch/elasticsearch:8.13.4")
#         container.with_env("discovery.type", "single-node")
#         container.start()
#
#         host = container.get_container_host_ip()
#         port = container.get_exposed_port(9200)
#         base_url = f"http://{host}:{port}"
#
#         ES_PROP["container"] = container
#         ES_PROP["base_url"] = base_url
#
#         ES_PROP["started"].set()
#
#         # time to give up to wait for green status (2mins from now)
#         time_to_give_up = time.time() + timeout
#         health_url = f"{base_url}/_cluster/health?wait_for_status=green&timeout=1s"
#         while time.time() < time_to_give_up:
#             try:
#                 r = requests.get(health_url, timeout=2)
#                 if r.status_code == 200 and r.json().get("status") == "green":
#                     ES_PROP["done"].set()
#                     return
#             except requests.RequestException:
#                 pass
#             time.sleep(0.5)
#
#         ES_PROP["error"] = RuntimeError("Elasticsearch status did not turn green")
#         ES_PROP["done"].set()
#
#     except Exception as e:
#         ES_PROP["error"] = e
#         ES_PROP["done"].set()
#
#
# @pytest.fixture(scope="session", autouse=True)
# def start_es_background():
#     """Start the ES container on a background thread at session start."""
#     t = threading.Thread(target=_start_container_in_thread, daemon=True)
#     t.start()
#
#     yield
#
#     container = ES_PROP.get("container")
#     if container:
#         container.stop()
#
#
# @pytest.fixture
# def es_base_url():
#     """Return base_url if container.start() has been called"""
#     ES_PROP["started"].wait(timeout=10)
#     if ES_PROP.get("error") and not ES_PROP.get("base_url"):
#         raise ES_PROP["error"]
#     return ES_PROP.get("base_url")
#
#
# @pytest_asyncio.fixture
# async def es_ready():
#     """Async fixture that waits for the ES cluster to be green or raises startup error."""
#     await asyncio_wait_for_thread_event(ES_PROP["started"], timeout=10)
#     if ES_PROP.get("error") and not ES_PROP.get("base_url"):
#         raise ES_PROP["error"]
#
#     await asyncio_wait_for_thread_event(ES_PROP["done"], timeout=120)
#
#     if ES_PROP.get("error"):
#         raise ES_PROP["error"]
#
#     base_url = ES_PROP.get("base_url")
#     if not base_url:
#         raise RuntimeError("Elasticsearch did not start correctly")
#     return base_url
#
#
# @pytest_asyncio.fixture
# async def es_client(es_ready):
#     """Elasticsearch client fixture."""
#     client = AsyncElasticsearch(hosts=[es_ready])
#     try:
#         yield client
#     finally:
#         await client.close()
#
#
# def asyncio_wait_for_thread_event(evt: threading.Event, timeout: float):
#     """Return coroutine that resolves when evt.wait() returns."""
#     return asyncio.wait_for(asyncio.to_thread(evt.wait, timeout), timeout=timeout)
