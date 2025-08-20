"""
This file declares the web API for the component. This is what gets called
by Merino, when we get a request to process.

"""

import aiodogstatsd

from merino.providers.suggest.skeleton.provider import SkeletonProvider, SkeletonBackend
from merino.providers.suggest.base import BaseSuggestion, SuggestionRequest
from merino.providers.suggest.skeleton.backends.emoji_picker.backend import (
    EmojiPickerBackend,
)
from merino.providers.suggest.skeleton.backends.emoji_picker.manifest import (
    EmojiManifest,
)


class EmojiProvider(SkeletonProvider):
    """This is the workhorse that provides responses to the request. We need
    to override any of the SkeletonProvider(BaseProvider) methods we want to
    customize."""

    backend: SkeletonBackend
    manifest_data: EmojiManifest | None

    async def query(self, sreq: SuggestionRequest) -> list[BaseSuggestion]:
        """Fetch the appropriate emojis for the given request."""
        # TODO: Add metric call here.
        return await EmojiPickerBackend().query(sreq.query)

    def __init__(
        self,
        metrics_client: aiodogstatsd.Client,
        backend: None | SkeletonBackend = None,
        name: str = "EmojiPicker",
        score: float = 0.5,
        query_timeout_sec: float = 0.5,
        enabled_by_default: bool = False,
    ):
        self.backend = backend or EmojiPickerBackend()

        super().__init__(
            backend=self.backend,
            metrics_client=metrics_client,
            score=score,
            name=name,
            query_timeout_sec=query_timeout_sec,
            enabled_by_default=enabled_by_default,
        )

    def initialize(self):
        """An abstract method to initialize data. This is called on request invocation."""
        self.manifest_data = EmojiManifest(domains=[], partners=[])
        pass

    async def fetch_manifest_data(self):
        """Get the latest version of the site metadata and store it in GCS. This will generally
        be called from a merino job.
        """
        if self.manifest_data:
            self.manifest_data.fetch_manifest_data()

    async def build_and_upload_manifest_file(self):
        """This function can be called by the `uv` jobs in order to build the site
        metadata file and upload it to GCS.

        Our example doesn't require this, so we don't have to build it.

        QQ: Shouldn't this be a class method for `EmojiManifest`?
        """
        if self.manifest_data:
            self.manifest_data.build_and_upload_manifest_file()
