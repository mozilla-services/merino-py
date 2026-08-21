"""Errors specific to the EmojiPicker"""

from merino.providers.suggest.skeleton.backends.errors import GeneralError


class EmojiPickerError(GeneralError):
    """Describe the errors that EmojiPicker can return.

    For now, there's just the one, GeneralError. We can wrap this
    so that we can do fun type checking logic.
    """

    pass
