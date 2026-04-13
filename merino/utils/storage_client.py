"""Shared GCS Client"""

from typing import Optional

from gcloud.aio.storage import Storage

from merino.configs import settings


_shared_storage_client: Optional[Storage] = None

def get_storage_client() -> Storage:  # pragma: no cover
    """Get or create a shared GCS client, reusing the 
    underlying aiohttp connection pool.
    """
    global _shared_storage_client
    url: str = settings.gcs.endpoint_url
    if _shared_storage_client is not None:
        return _shared_storage_client
    # Use locahost override if set, otherwise the default google api
    _shared_storage_client = Storage(api_root=url) if url else Storage()
    return _shared_storage_client
