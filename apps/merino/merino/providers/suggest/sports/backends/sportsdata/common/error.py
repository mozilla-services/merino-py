"""High level error wrappers for Sports"""


# Errors
class SportsDataError(Exception):
    """Significant error occurring with Sports"""

    message: str

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message

    def __str__(self):
        name = type(self).__name__
        return f"{name}: {self.message}"


class SportsDataWarning(Exception):
    """Cautionary error occurring with Sports"""

    message: str

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message

    def __str__(self):
        name = type(self).__name__
        return f"{name}: {self.message}"
