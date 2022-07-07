from urllib.parse import urljoin
import kinto_http
import requests

class Client(object):
    attachment_host: str = ""
    host: str = "https://firefox.settings.services.mozilla.com"

    def __init__(self) -> None:
        self.client = kinto_http.Client(server_url=self.host)
        self.attachment_host = self.client.server_info()["capabilities"]["attachments"]["base_url"]

    def get(self, bucket, collection):
        return self.client.get_records(collection=collection, bucket=bucket)

    def fetch_attachment(self, attachement_uri):
        uri = urljoin(self.attachment_host, attachement_uri)
        return requests.get(uri)
