"""Errors specific to the SportsDataPicker"""

from merino.exceptions import BackendError


class SportsDataError(BackendError):
    """Describe the errors that SportsDataPicker can return.
    For now, there's just the one, GeneralError. We can wrap this
    so that we can do fun type checking logic.
    """

    def __init__(self, msg: str):
        self.message = msg
        super().__init__()

    def __str__(self):
        name = type(self).__name__
        return f"{name}: self.msg"


class SportsDataWarning(BackendError):
    """Describe the errors that SportsDataPicker can return.
    For now, there's just the one, GeneralError. We can wrap this
    so that we can do fun type checking logic.
    """

    def __init__(self, msg: str):
        self.message = msg
        super().__init__()

    def __str__(self):
        name = type(self).__name__
        return f"{name}: self.msg"
