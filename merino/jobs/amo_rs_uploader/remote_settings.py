"""A simple remote settings client"""
from asyncio import Task, TaskGroup
from typing import Any

from httpx import AsyncClient


class RemoteSettings:
    """A simple remote settings client"""

    server: str
    workspace: str
    cid: str
    auth: str

    def __init__(self, server: str, workspace: str, cid: str, auth: str):
        """Initialize RemoteSettings"""
        self.server = server
        self.workspace = workspace
        self.cid = cid
        self.auth = auth

    async def upload_record(self, client: AsyncClient, record: dict[str, Any]):
        """Upload a single record"""
        url = (
            f"{self.server}/buckets/{self.workspace}/collections/{self.cid}/"
            f"records/{record['id']}"
        )
        res = await client.put(
            url,
            json={"data": record},
            headers={
                "Content-Type": "application/json",
                "Authorization": self.auth,
            },
        )
        res.raise_for_status()

    async def upload_records(self, records: list[dict[str, Any]]):
        """Upload multiple records"""
        tasks: list[Task] = []

        async with (AsyncClient() as client, TaskGroup() as group):
            for record in records:
                tasks.append(
                    group.create_task(
                        self.upload_record(client, record), name=record["id"]
                    )
                )

        for task in tasks:
            await task
