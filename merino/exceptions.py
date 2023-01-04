"""Merino specific exceptions."""


class BackendError(Exception):
    """Error specific to provider backend functions."""


class InvalidProviderError(Exception):
    """Raised when an unknown provider encountered."""

    pass
