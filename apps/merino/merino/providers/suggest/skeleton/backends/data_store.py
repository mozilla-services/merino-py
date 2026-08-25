"""Generic Data Storage system

This is a placeholder for whatever long term data storage system you wish to use. It is
strongly suggested that you use one of the common data storage systems (e.g. Elasticsearch,
Redis, etc.) and that you wrap that data store with whatever configurations you need here.

"""

from abc import ABC
from merino.exceptions import BackendError


class SkeletonDataError(BackendError):
    """General error class for this storage engine"""


class SkeletonDataStore(ABC):
    """Generic storage engine. Replace with a more appropriate storage system."""

    # These are the credentials you wish to use. It is suggested that you
    # use a specific Credentials class which is able to potentially gather the credentials
    # from multiple sources, but for now, we'll use a simple dictionary.
    credentials: dict[str, str]

    def __init__(self, credentials: dict[str, str]):
        """Create an instance of the storage engine. This method will be called during
        application instantiation, so you should _not_ call any blocking or fatal methods, unless
        they are critical enough to prevent Merino from starting.
        """
        self.credentials = credentials
        pass

    async def startup(self) -> None:
        """Perform the start-up functions, including connecting to the data stores. Note that this
        method may be called from different contexts. Remember `jobs` are READ/WRITE, where `suggest`
        is `READ ONLY`.
        """
        pass

    async def shutdown(self) -> None:
        """Politely close connections, clean up caches, and other janitorial tasks, if required"""
        pass

    async def search(self, query: str, *args, **kwargs) -> dict[str, str]:
        """Search the store and return relevant results"""
        return dict()

    # Additional methods may be needed, (e.g. ones to `initialize_database()` or `create_indexes()`)
    # These are left as an exercise for the reader.
