"""Async client that usese community maintained gcloud-aio library to interact with Google Cloud Storage"""

import logging
import orjson
from orjson import JSONDecodeError

from gcloud.aio.storage import Storage
from merino.web.models_v1 import Manifest


logger = logging.getLogger(__name__)


class AsyncGcsClient:
    """Class that provides wrapper functions around gcloud-aio-storage functions. More functionality to be added."""

    storage: Storage

    def __init__(self) -> None:
        self.storage = Storage()

    async def get_manifest_from_blob(self, bucket_name: str, blob_name: str) -> Manifest | None:
        """Download the top pick blob from the bucket and return as Manifest object"""
        manifest = None
        try:
            top_picks_blob = await self.storage.download(bucket_name, blob_name)
            if top_picks_blob is not None:
                manifest = Manifest(**orjson.loads(top_picks_blob))
        except JSONDecodeError:
            logger.error(f"Tried to load invalid json for blob: {blob_name}")
            return manifest
        except Exception as ex:
            logger.error(f"Unexpected error when downloading blob: {ex}")
            return manifest

        await self.close_client()

        logger.info("Succussfully downloaded manifest blob via async client")
        return manifest

    async def close_client(self):
        await self.storage.close()
