"""Protocol definitions for the example "Emoji Picker"

This should include various data type and derivatives that your example class requires.

"""

import json

from merino.providers.suggest.base import BaseSuggestion
from merino.providers.suggest.skeleton import SkeletonData


class EmojiSuggestion(BaseSuggestion):
    """The Returned Suggestion. `BaseSuggestion` is an object description, and backends
    should provide an instantiated version that can be referenced.

    You may wish to include additional functions that do things like custom rendering, altering
    data values for publication, etc.

    """

    pass


class EmojiData(SkeletonData):
    """The contained result we want to return to the Web API"""

    emoji: str = ""
    description: str = ""

    def __init__(
        self,
        emoji: str = "🤷",
        description: str = "A person shrugging",
        *args,
        **kwargs,
    ):
        """Since this is based off of BaseModel, we need to specify the values
        as part of the __init__. This examples show an over-ride of the initial
        values.

        """
        super().__init__(*args, emoji=emoji, description=description, **kwargs)

    def as_suggestion(self) -> BaseSuggestion:
        """Normalize whatever data we might be using into a standard Suggestion"""
        return EmojiSuggestion(
            title=self.emoji,
            description=self.description,
            url=self.url,
            provider=self.provider,
            is_sponsored=False,
            score=self.score,
        )
