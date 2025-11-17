"""This file declares the web API for the component. This is what gets called
by Merino, when we get a request to process.

"""

import aiodogstatsd

from merino.providers.manifest.backends.protocol import ManifestData
from merino.providers.suggest.skeleton.provider import SkeletonProvider
from merino.providers.suggest.base import BaseSuggestion, SuggestionRequest
from merino.providers.suggest.skeleton.backends.emoji_picker.backend import (
    EmojiPickerBackend,
)


class EmojiProvider(SkeletonProvider):
    """This is the workhorse that provides responses to the request. We need
    to override any of the SkeletonProvider(BaseProvider) methods we want to
    customize.

    See the base class for additional functions

    """

    backend: EmojiPickerBackend

    def __init__(
        self,
        metrics_client: aiodogstatsd.Client,
        backend: EmojiPickerBackend,
        name: str = "EmojiPicker",
        score: float = 0.5,
        query_timeout_sec: float = 0.5,
        enabled_by_default: bool = False,
    ):
        # Define our manifest data here. It's fairly early, but we need that data defined
        # and included with the backend to ensure that types are properly set.
        self.manifest_data = ManifestData(domains=[], partners=[])
        self.backend = backend

        super().__init__(
            backend=self.backend,
            metrics_client=metrics_client,
            score=score,
            name=name,
            query_timeout_sec=query_timeout_sec,
            enabled_by_default=enabled_by_default,
        )

    def initialize(self):
        """Create connections, components and other actions needed when starting up. This is called"""
        pass

    async def query(self, sreq: SuggestionRequest) -> list[BaseSuggestion]:
        """Fetch the appropriate emojis for the given request."""
        # TODO: Add metric call here.

        return await self.backend.query(sreq.query)

    async def fetch_manifest_data(self) -> ManifestData:
        """Get the latest version of the site metadata and store it in GCS. This will generally
        be called from a merino job.

        """
        # Perform the functions to fetch and set the Manifest data (e.g. update domains and partners)
        return self.manifest_data

    async def build_and_upload_manifest_file(self):
        """Build the site metadata file and upload it to GCS.

        This call is made by the `uv` jobs. Our example doesn't require this, so we don't have to build it.

        """
        pass

    def normalize_query(self, query: str) -> str:
        """Format the query, replacing the `query` string in SuggestionRequest"""
        return super().normalize_query(query)

    def validate(self, srequest: SuggestionRequest) -> None:
        """Validate that the SuggestionRequest is correct, this can involve values outside of the `query` string."""
        return super().validate(srequest)
