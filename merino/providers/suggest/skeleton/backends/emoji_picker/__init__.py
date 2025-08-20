"""Because this is a skeleton/example, let's create a single "backend" that
can illustrate what multiple providers might look like. (e.g. if we had
different sources of emoji we were coordinating.)
"""

from merino.providers.suggest.skeleton.backends.emoji_picker.backend import (
    EmojiPickerBackend,
)
from merino.providers.suggest.skeleton.backends.emoji_picker.errors import (
    EmojiPickerError,
)
