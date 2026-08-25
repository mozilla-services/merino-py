"""Public interface for the search term submission message handler.

Exposes the process-wide ``MessageHandler`` singleton and its lifecycle functions
"""

from merino.message_handlers.search_terms.handler import MessageHandler

__all__ = [
    "MessageHandler",
    "SUBMISSION_FLAG",
    "message_handler",
    "start",
    "stop",
    "get_message_handler",
]

SUBMISSION_FLAG = "search-term-submission"

# The message handler singleton. Use `start()` and `stop()` to interact with it.
message_handler: MessageHandler = MessageHandler()


async def start() -> None:
    """Start the message handler. This should only be called once at startup."""
    await message_handler.start()


async def stop() -> None:
    """Drain and stop the message handler. This should only be called once at shutdown."""
    await message_handler.stop()


def get_message_handler() -> MessageHandler:
    """Return the message handler singleton."""
    return message_handler
