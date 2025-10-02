"""High level error wrappers for Sports"""


# Errors
class SportsDataError(BaseException):
    """Significant error occurring with Sports"""

    message: str

    def __init__(self, message: str):
        self.message = message

    def __str__(self):
        name = type(self).__name__
        return f"{name}: {self.message}"


class SportsDataWarning(BaseException):
    """Cautionary error occurring with Sports"""

    message: str

    def __init__(self, message: str):
        self.message = message

    def __str__(self):
        name = type(self).__name__
        return f"{name}: {self.message}"
