"""Public interface for the search term sanitization message handler.

Exposes the process-wide ``MessageHandler`` singleton and its lifecycle functions.
The handler is a singleton because its ``AsyncBatchQueue`` registers OpenTelemetry
instruments for the life of the meter provider, so short-lived instances would pin
them in memory and emit duplicate-instrument warnings.
"""

from merino_fleece.message_handlers.search_terms.handler import MessageHandler

__all__ = ["MessageHandler", "message_handler", "start", "stop", "get_message_handler"]

# The message handler singleton. Use `start()` and `stop()` to interact with it.
message_handler: MessageHandler = MessageHandler()


async def start() -> None:
    """Start the message handler. This should only be called once at startup."""
    await message_handler.start()


async def stop() -> None:
    """Drain and stop the message handler. This should only be called once at shutdown."""
    await message_handler.stop()


def get_message_handler() -> MessageHandler:
    """Return the message handler singleton. Intended for use with ``fastapi.Depends``."""
    return message_handler
