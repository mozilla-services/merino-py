from urllib.parse import urljoin

import httpx
import kinto_http

from merino.config import settings


class Client:
    client: kinto_http.AsyncClient
    attachment_host: str = ""

    def __init__(self) -> None:
        self.client = kinto_http.AsyncClient(server_url=settings.remote_settings.server)

    async def fetch_attachment_host(self) -> str:
        server_info = await self.client.server_info()
        return server_info["capabilities"]["attachments"]["base_url"]

    async def get(self, bucket, collection) -> list[dict]:
        return await self.client.get_records(collection=collection, bucket=bucket)

    async def fetch_attachment(self, attachement_uri) -> httpx.Response:
        if not self.attachment_host:
            self.attachment_host = await self.fetch_attachment_host()
        uri = urljoin(self.attachment_host, attachement_uri)
        async with httpx.AsyncClient() as client:
            return await client.get(uri)

    def get_icon_url(self, icon_uri: str) -> str:
        return urljoin(self.attachment_host, icon_uri)
