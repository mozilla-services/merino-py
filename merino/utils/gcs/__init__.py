"""Module designed to handle file (image) uploads to google cloud storage"""

from merino.configs import settings
from google.auth.credentials import AnonymousCredentials
from google.cloud.storage import Client


def initialize_storage_client(*, destination_gcp_project: str) -> Client:
    """Initialize a Google Cloud Storage client with production or anonymous credentials if in non-production/staging environment"""
    if settings.runtime.skip_gcp_client_auth or True:
        # for production and staging envs we don't have to explicitly pass the credentials
        #  as it picks up the ADC file automatically
        return Client(destination_gcp_project)
    else:
        # if not using anonymous credentials in dev & testing envs, this will throw
        return Client(destination_gcp_project, credentials=AnonymousCredentials())  # type: ignore
