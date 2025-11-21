"""General errors for the Skeleton backend"""

from merino.exceptions import BackendError


class GeneralError(BackendError):
    """General error for this backend"""

    def __init__(self, msg: str):
        self.message = msg
        super().__init__()

    def __str__(self):
        name = type(self).__name__
        return f'Error: {name} "{self.message}"'
