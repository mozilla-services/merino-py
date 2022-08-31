"""RemoteSettings Client"""
from urllib.parse import urljoin

import httpx
import kinto_http

from merino.config import settings


class Client:
    """Remote Settings Client Class."""

    client: kinto_http.AsyncClient
    attachment_host: str = ""

    def __init__(self) -> None:
        """Init Remote Settings Client"""
        self.client = kinto_http.AsyncClient(server_url=settings.remote_settings.server)

    async def fetch_attachment_host(self) -> str:
        """TODO: Get attachment host"""
        server_info = await self.client.server_info()
        return server_info["capabilities"]["attachments"]["base_url"]

    async def get(self, bucket, collection) -> list[dict]:
        """TODO: Get records from specified collection and bucket"""
        return await self.client.get_records(collection=collection, bucket=bucket)

    async def fetch_attachment(self, attachement_uri) -> httpx.Response:
        """TODO: Get attachment"""
        if not self.attachment_host:
            self.attachment_host = await self.fetch_attachment_host()
        uri = urljoin(self.attachment_host, attachement_uri)
        async with httpx.AsyncClient() as client:
            return await client.get(uri)

    def get_icon_url(self, icon_uri: str) -> str:
        """TODO: Get Icon Url"""
        return urljoin(self.attachment_host, icon_uri)
