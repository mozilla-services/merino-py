# Errors
class SportDataError(BaseException):
    message: str

    def __init__(self, message: str):
        self.message = message

    def __str__(self):
        name = type(self).__name__
        return f"{name}: {self.message}"


class SportDataWarning(BaseException):
    message: str

    def __init__(self, message: str):
        self.message = message

    def __str__(self):
        name = type(self).__name__
        return f"{name}: {self.message}"
