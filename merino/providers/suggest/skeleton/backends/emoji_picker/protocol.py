"""Protocol definitions for the example "Emoji Picker"

This should include various data type and derivatives that your example class requires.

"""

from merino.providers.suggest.base import BaseSuggestion
from merino.providers.suggest.skeleton import SkeletonData


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
        return BaseSuggestion(
            title=self.emoji,
            description=self.description,
            url=self.url,
            provider=self.provider,
            is_sponsored=False,
            score=self.score,
        )
