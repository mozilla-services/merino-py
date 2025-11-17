"""Silly example emoji picker"""

from merino.providers.suggest.base import BaseSuggestion
from merino.providers.suggest.skeleton.backends.data_store import SkeletonDataStore
from merino.providers.suggest.skeleton.backends.emoji_picker.protocol import (
    EmojiData,
    EmojiPickerProtocol,
)


class EmojiPickerBackend(EmojiPickerProtocol):
    """Provide the methods specific to this provider for fulfilling the request"""

    data_store: SkeletonDataStore

    def __init__(
        self,
        store: SkeletonDataStore,
        max_suggestions: int = 10,
        *args,
        **kwargs,
    ):
        self.data_store = store
        self.max_suggestions = max_suggestions

    async def query(self, description: str | None = None) -> list[BaseSuggestion]:
        """Eventually use clever logic in order to return an emoji specific to the
        passed description string, but for now, just return the default in a list.

        """
        return [EmojiData().as_suggestion()]

    async def startup(self) -> None:
        """Perform whatever startup functions are required, (e.g. data store connections and initializations)"""
        pass

    async def shutdown(self) -> None:
        """Perform whatever shutdown functions are required. (e.g. data store releases, cache clearing, etc.)"""
        pass
