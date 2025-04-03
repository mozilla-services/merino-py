"""Module implementing an async stale-while-revalidate caching decorator with request coalescing."""

import asyncio
import functools
import logging
import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable, Dict, Set, TypeVar, Generic, ParamSpec, Coroutine
from merino.exceptions import BackendError

V = TypeVar("V")  # Generic type for values stored in the cache
CacheKey = str

logger = logging.getLogger(__name__)


def key_builder(
    func: Callable[..., Awaitable[V]],
    args: tuple[Any, ...],
    kwargs: Dict[str, Any],
) -> CacheKey:
    """Build a cache key based on the function's name, positional arguments (without self), and keyword arguments.

    Args:
        func: The decorated function.
        args: Positional arguments.
        kwargs: Keyword arguments.

    Returns:
        A string representing the cache key.
    """
    ordered_kwargs = sorted(kwargs.items())
    return func.__name__ + str(args[1:]) + str(ordered_kwargs)  # args[1:] excludes `self`


@dataclass
class CacheEntry(Generic[V]):
    """Container for a cached value and its expiration time, with an associated lock.

    Attributes:
        value: The cached value.
        expiration: The time when the cached value expires.
        lock: A lock to coordinate concurrent updates.
    """

    value: V | None
    expiration: datetime
    lock: asyncio.Lock


class WaitRandomExpiration:
    """Computes a random expiration time within a specified range.

    Attributes:
        ttl_min: Minimum time-to-live.
        ttl_max: Maximum time-to-live.
    """

    def __init__(self, ttl_min: timedelta, ttl_max: timedelta) -> None:
        self.ttl_min = ttl_min
        self.ttl_max = ttl_max

    def __call__(self) -> datetime:
        """Compute and return a new expiration time.

        Returns:
            A datetime representing the expiration time.
        """
        seconds = random.uniform(self.ttl_min.total_seconds(), self.ttl_max.total_seconds())
        return datetime.now() + timedelta(seconds=seconds)


async def _fetch_and_store(
    func: Callable[..., Awaitable[V]],
    entry: CacheEntry[V],
    args: tuple[Any, ...],
    kwargs: Dict[str, Any],
    wait_expiration: WaitRandomExpiration,
) -> V:
    """Call the decorated function and update the cache entry.

    Args:
        func: The decorated function.
        entry: The cache entry to update.
        args: Positional arguments.
        kwargs: Keyword arguments.
        wait_expiration: Object to compute expiration times.

    Returns:
        The result of the function call.
    """
    result = await func(*args, **kwargs)
    entry.value = result
    entry.expiration = wait_expiration()
    return result


async def _get_or_update_cache(
    func: Callable[..., Awaitable[V]],
    key: CacheKey,
    args: tuple[Any, ...],
    kwargs: Dict[str, Any],
    wait_expiration: WaitRandomExpiration,
    cache_obj: Dict[CacheKey, CacheEntry[V]],
    jobs_obj: Set[asyncio.Task],
) -> V:
    """Retrieve a fresh value from the cache or update it if stale.

    If the entry is stale, a background update is scheduled while returning the stale value.
    If no entry exists, the value is computed and stored.

    Args:
        func: The decorated function.
        key: The cache key.
        args: Positional arguments.
        kwargs: Keyword arguments.
        wait_expiration: Object to compute expiration times.
        cache_obj: The cache storage.
        jobs_obj: The set of background jobs.

    Returns:
        The cached or computed result.
    """
    if key in cache_obj:
        entry = cache_obj[key]
        if datetime.now() > entry.expiration and not entry.lock.locked():
            task = asyncio.create_task(
                _update_cache(func, key, args, kwargs, wait_expiration, cache_obj)
            )
            jobs_obj.add(task)
            task.add_done_callback(lambda t: jobs_obj.discard(t))

        # Return a stale value immediately if possible, otherwise, wait for the background task.
        if entry.value is not None:
            return entry.value
        else:
            await asyncio.sleep(0.1)  # Small sleep to allow the background task to grab the lock.
            # Wait for the background task to finish and return the value if it exists.
            async with entry.lock:
                if entry.value is not None:
                    # This line is reached if the background task successfully updated the cache.
                    return entry.value  # type: ignore[unreachable]
                else:
                    # This line is reached if the update failed, and there was no stale value.
                    raise BackendError(f"Failed to obtain value for {key}")
    else:
        # This is the first request for this cache key, so an entry must be created.
        entry = CacheEntry(value=None, expiration=datetime.min, lock=asyncio.Lock())
        cache_obj[key] = entry
        async with entry.lock:
            if datetime.now() < entry.expiration and entry.value is not None:
                return entry.value
            return await _fetch_and_store(func, entry, args, kwargs, wait_expiration)


async def _update_cache(
    func: Callable[..., Awaitable[V]],
    key: CacheKey,
    args: tuple[Any, ...],
    kwargs: Dict[str, Any],
    wait_expiration: WaitRandomExpiration,
    cache_obj: Dict[CacheKey, CacheEntry[V]],
) -> None:
    """Update a stale cache entry by calling the decorated function while holding the entry's lock.

    Args:
        func: The decorated function.
        key: The cache key.
        args: Positional arguments.
        kwargs: Keyword arguments.
        wait_expiration: Object to compute expiration times.
        cache_obj: The cache storage.
    """
    entry = cache_obj[key]
    async with entry.lock:
        if datetime.now() < entry.expiration and entry.value is not None:
            return
        try:
            await _fetch_and_store(func, entry, args, kwargs, wait_expiration)
        except Exception as e:
            if entry.value is not None:
                logger.error(f"Error updating cache for key {key}: {e}. Returning stale data.")
            else:
                raise


P = ParamSpec("P")  # Generic parameter for the decorated function's parameters


def stale_while_revalidate(
    wait_expiration: WaitRandomExpiration,
    cache: Callable[[Any], Dict[CacheKey, CacheEntry[V]]],
    jobs: Callable[[Any], Set[asyncio.Task]],
) -> Callable[[Callable[P, Awaitable[V]]], Callable[P, Coroutine[Any, Any, V]]]:
    """Decorate a function to use stale-while-revalidate caching and request coalescing.

    Args:
        wait_expiration: Object to compute expiration times.
        cache: Callable that returns the cache storage given the instance.
        jobs: Callable that returns the set of background tasks given the instance.
        logger: Logger for error messages.

    Returns:
        A decorator function. What the type hint means, is that it converts an async function
        `(Callable[P, Awaitable[V]])` to a new async function `(Callable[P, Coroutine[Any, Any, V]])`
        with the same parameters and return type.
    """

    def decorator(func: Callable[P, Awaitable[V]]) -> Callable[P, Coroutine[Any, Any, V]]:
        """Decorate an async function.
        - The decorator accepts a function (func) that takes some parameters (P, which stands for "parameters")
          and returns an Awaitable that eventually produces a value of type V.
        - The decorator then returns a new function that accepts the same parameters (P) but returns a Coroutine
          (an async function) which will eventually yield a value of type V.
        """

        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> V:
            """Retrieve a cached value or compute and store a new value."""
            self_instance = args[0] if args else None
            if self_instance is None:
                raise ValueError("The decorated function must be a method (self is required).")
            key = key_builder(func, args, kwargs)
            cache_obj = cache(self_instance)
            jobs_obj = jobs(self_instance)
            return await _get_or_update_cache(
                func, key, args, kwargs, wait_expiration, cache_obj, jobs_obj
            )

        return wrapper

    return decorator
