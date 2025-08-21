"""This file declares the web API for the component. This is what gets called
by Merino, when we get a request to process.

"""

import aiodogstatsd

from merino.providers.suggest.skeleton import SkeletonBackend
from merino.providers.suggest.skeleton.provider import SkeletonProvider
from merino.providers.suggest.base import BaseSuggestion, SuggestionRequest
from merino.providers.suggest.skeleton.backends.emoji_picker.backend import (
    EmojiPickerBackend,
)
from merino.providers.suggest.skeleton.backends.manifest import (
    SkeletonManifest,
)


class EmojiProvider(SkeletonProvider):
    """This is the workhorse that provides responses to the request. We need
    to override any of the SkeletonProvider(BaseProvider) methods we want to
    customize.

    """

    backend: SkeletonBackend

    async def query(self, sreq: SuggestionRequest) -> list[BaseSuggestion]:
        """Fetch the appropriate emojis for the given request."""
        # TODO: Add metric call here.
        picker: EmojiPickerBackend = EmojiPickerBackend(self.backend.manifest_data)
        return await picker.query(sreq.query)

    def __init__(
        self,
        metrics_client: aiodogstatsd.Client,
        backend: None | SkeletonBackend = None,
        name: str = "EmojiPicker",
        score: float = 0.5,
        query_timeout_sec: float = 0.5,
        enabled_by_default: bool = False,
    ):
        # Define our manifest data here. It's fairly early, but we need that data defined
        # and included with the backend to ensure that types are properly set.
        self.manifest_data = SkeletonManifest(domains=[], partners=[])
        self.backend = backend or EmojiPickerBackend(manifest_data=self.manifest_data)

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

    async def fetch_manifest_data(self):
        """Get the latest version of the site metadata and store it in GCS. This will generally
        be called from a merino job.

        """
        if self.manifest_data:
            self.backend.manifest_data.fetch_manifest_data()

    async def build_and_upload_manifest_file(self):
        """Build the site metadata file and upload it to GCS.

        This call is made by the `uv` jobs. Our example doesn't require this, so we don't have to build it.

        """
        if self.backend.manifest_data:
            self.backend.manifest_data.build_and_upload_manifest_file()
