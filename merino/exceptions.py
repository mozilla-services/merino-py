"""Merino specific exceptions."""


class InvalidProviderError(Exception):
    """Raised when an unknown provider encountered."""

    pass


class InvalidGitRepository(Exception):
    """Exception to handle invalid Git Repository."""

    pass
