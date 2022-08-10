from urllib.parse import urljoin

import kinto_http
import requests

from merino.config import settings


class Client:
    attachment_host: str = ""

    def __init__(self) -> None:
        self.client = kinto_http.Client(server_url=settings.remote_settings.server)
        self.attachment_host = self.client.server_info()["capabilities"]["attachments"][
            "base_url"
        ]

    def get(self, bucket, collection):
        return self.client.get_records(collection=collection, bucket=bucket)

    def fetch_attachment(self, attachement_uri):
        uri = urljoin(self.attachment_host, attachement_uri)
        return requests.get(uri)

    def get_icon_url(self, icon_uri: str) -> str:
        return urljoin(self.attachment_host, icon_uri)
