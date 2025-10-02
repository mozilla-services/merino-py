"""High level error wrappers for Sports"""


# Errors
class SportDataError(BaseException):
    """Significant error occurring with Sports"""

    message: str

    def __init__(self, message: str):
        self.message = message

    def __str__(self):
        name = type(self).__name__
        return f"{name}: {self.message}"


class SportDataWarning(BaseException):
    """Cautionary error occurring with Sports"""

    message: str

    def __init__(self, message: str):
        self.message = message

    def __str__(self):
        name = type(self).__name__
        return f"{name}: {self.message}"
