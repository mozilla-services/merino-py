"""Errors raised by the search term submission message handler."""

from merino.exceptions import BackendError


class FleeceError(BackendError):
    """Error raised when submitting search terms to merino-fleece fails."""
