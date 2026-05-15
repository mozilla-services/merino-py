"""Pytest unit tests for default_key_builder function."""

import asyncio
import logging
from datetime import datetime, timedelta

import pytest
from freezegun import freeze_time

from merino.curated_recommendations.corpus_backends.caching import (
    stale_while_revalidate,
    key_builder,
    WaitRandomExpiration,
)


class TestKeyBuilder:
    """Tests for the default_key_builder function."""

    async def dummy_function(self, *args, **kwargs):
        """Return without taking any action."""
        pass

    class Dummy:
        """A dummy class with a fixed repr for testing."""

        def __repr__(self):
            """Return a fixed string representation."""
            return "Dummy()"

    def test_empty_args_kwargs(self):
        """Test default key with no args or kwargs."""
        expected = "dummy_function()[]"
        result = key_builder(self.dummy_function, (self,), {})
        assert result == expected

    def test_with_positional_args(self):
        """Test default key with only positional args."""
        expected = "dummy_function(1, 2, 3)[]"
        result = key_builder(self.dummy_function, (self, 1, 2, 3), {})
        assert result == expected

    def test_with_keyword_args(self):
        """Test default key with only keyword args."""
        expected = "dummy_function()[('a', 1), ('b', 2)]"
        result = key_builder(self.dummy_function, (self,), {"b": 2, "a": 1})
        assert result == expected

    def test_with_args_and_kwargs(self):
        """Test default key with both positional and keyword args."""
        expected = "dummy_function(1,)[('m', 13), ('z', 26)]"
        result = key_builder(self.dummy_function, (self, 1), {"z": 26, "m": 13})
        assert result == expected

    def test_kwargs_order_independence(self):
        """Test that unordered keyword args yield the same key."""
        key1 = key_builder(self.dummy_function, (self, 1), {"a": 1, "b": 2})
        key2 = key_builder(self.dummy_function, (self, 1), {"b": 2, "a": 1})
        assert key1 == key2

    def test_with_different_types(self):
        """Test default key with various types in args and kwargs."""
        args = (self, 42, 3.14, True, None, "hello", [1, 2, 3], {"key": "value"})
        kwargs = {"a": 10, "b": [4, 5], "c": {"nested": "dict"}}
        expected = (
            "dummy_function(42, 3.14, True, None, 'hello', [1, 2, 3], "
            "{'key': 'value'})[('a', 10), ('b', [4, 5]), ('c', {'nested': 'dict'})]"
        )
        result = key_builder(self.dummy_function, args, kwargs)
        assert result == expected

    def test_with_custom_object(self):
        """Test default key with a custom object in args and kwargs."""
        foo = self.Dummy()
        expected = "dummy_function(Dummy(),)[('x', Dummy())]"
        result = key_builder(self.dummy_function, (self, foo), {"x": foo})
        assert result == expected


@freeze_time("2025-01-01 00:00:00")
class TestWaitRandomExpiration:
    """Tests for the WaitRandomExpiration class."""

    def test_expiration_range(self):
        """Test that the expiration time is within the expected range."""
        ttl_min = timedelta(seconds=5)
        ttl_max = timedelta(seconds=10)
        frozen_time = datetime.now()  # frozen by freezegun
        wait_exp = WaitRandomExpiration(ttl_min, ttl_max)
        result = wait_exp()
        delta = (result - frozen_time).total_seconds()
        assert ttl_min.total_seconds() <= delta <= ttl_max.total_seconds()

    def test_randomness(self):
        """Test that multiple calls yield different expiration times."""
        ttl_min = timedelta(seconds=5)
        ttl_max = timedelta(seconds=10)
        wait_exp = WaitRandomExpiration(ttl_min, ttl_max)
        n = 10
        expirations = [wait_exp() for _ in range(n)]
        # Since the expiration time is uniformly random between 5 and 10 seconds,
        # the probability that any two generated times are exactly the same is essentially 0.
        unique_offsets = {(exp - datetime.now()).total_seconds() for exp in expirations}
        assert len(unique_offsets) == n


class TestStaleWhileRevalidate:
    """Test suite for the stale_while_revalidate decorator."""

    def setup_method(self):
        """Initialize test instance with cache, job set, and counters."""
        self._cache = {}
        self._jobs = set()
        self.call_count = 0

    # Use a fixed wait expiration that returns a future time.
    wait_exp = WaitRandomExpiration(timedelta(seconds=60), timedelta(seconds=120))
    # Simulated duration of a backend call in the test helpers below.
    backend_call_duration = 0.005

    @stale_while_revalidate(wait_exp, lambda self: self._cache, lambda self: self._jobs)
    async def compute_value(self, x):
        """Compute and return x multiplied by 2."""
        self.call_count += 1
        await asyncio.sleep(self.backend_call_duration)
        return x * 2

    @stale_while_revalidate(wait_exp, lambda self: self._cache, lambda self: self._jobs)
    async def failing_compute(self, x):
        """Compute and always raise an error."""
        self.call_count += 1
        await asyncio.sleep(self.backend_call_duration)
        raise ValueError("Computation failed")

    @stale_while_revalidate(wait_exp, lambda self: self._cache, lambda self: self._jobs)
    async def failing_compute_after_first_call(self, x):
        """Compute and return x multiplied by 3 on first call, then raise an error on subsequent calls."""
        self.call_count += 1
        await asyncio.sleep(self.backend_call_duration)
        if self.call_count > 1:
            raise ValueError("Computation failed after first call")
        return x * 3

    @pytest.mark.asyncio
    @freeze_time("2022-01-01 00:00:00", tick=True)
    async def test_initial_and_cached(self):
        """Compute value initially and return cached fresh value on subsequent calls."""
        result1 = await self.compute_value(10)
        assert result1 == 20
        assert self.call_count == 1

        # Second call should return the cached value without recomputation.
        result2 = await self.compute_value(10)
        assert result2 == 20
        assert self.call_count == 1

    @pytest.mark.asyncio
    async def test_stale_update_stampede(self):
        """Simulate a stampede on a stale cache and trigger only one background update."""
        # Freeze time with ticking enabled to control time.
        with freeze_time("2022-01-01 00:00:00", tick=True) as frozen_datetime:
            # Compute initial value to populate cache.
            result1 = await self.compute_value(10)
            assert result1 == 20
            assert self.call_count == 1

            # Advance time beyond the expiration (advance >120s) to force staleness.
            frozen_datetime.tick(121.0)

            n = 1000
            tasks = [asyncio.create_task(self.compute_value(10)) for _ in range(n)]
            results = await asyncio.gather(*tasks)
            # All concurrent calls should return the stale value immediately.
            for res in results:
                assert res == 20
            # Allow background update tasks to complete.
            await asyncio.gather(*self._jobs)

        # Verify that only one additional background update occurred.
        assert self.call_count == 2

    @pytest.mark.asyncio
    @freeze_time("2022-01-01 00:00:00", tick=True)
    async def test_stampede_on_startup(self):
        """Simulate a stampede on startup ensuring only one computation occurs."""
        # Launch concurrent calls without any pre-populated cache.
        n = 1000
        tasks = [asyncio.create_task(self.compute_value(10)) for _ in range(n)]
        results = await asyncio.gather(*tasks)
        for res in results:
            assert res == 20
        # Only one initial computation should have occurred.
        assert self.call_count == 1

    @pytest.mark.asyncio
    async def test_error_during_update_with_stale(self, caplog):
        """Return stale value and log error when a background update fails."""
        with freeze_time("2022-01-01 00:00:00", tick=True) as frozen_datetime:
            result1 = await self.failing_compute_after_first_call(5)
            assert result1 == 15

            frozen_datetime.tick(121.0)  # Force staleness. Max ttl is 120 seconds.
            result2 = await self.failing_compute_after_first_call(5)
            assert result2 == 15
            # 2x margin for event loop overhead
            await asyncio.sleep(2 * self.backend_call_duration)

        assert any(
            record.message
            == "Error updating cache for key failing_compute_after_first_call(5,)[]:"
            " Computation failed after first call. Returning stale data."
            and record.levelno == logging.ERROR
            for record in caplog.records
        )

    @pytest.mark.asyncio
    @freeze_time("2022-01-01 00:00:00", tick=True)
    async def test_error_during_update_without_stale(self):
        """Propagate error when no cached value exists during an update failure."""
        with pytest.raises(ValueError):
            await self.failing_compute(3)

    @pytest.mark.asyncio
    async def test_failed_update_does_not_cause_retry_storm(self):
        """Verify that failed cache updates extend expiration to prevent retry storms.

        When _update_cache fails and stale data exists, entry.expiration is
        extended to rate-limit retries to once per TTL window. Without this,
        every subsequent request would trigger a new update attempt.

        Regression test for the Feb 21 2026 curated-corpus-api outage.
        See: https://docs.google.com/document/d/1O0KXJlklGcQzr2CYb3MTGyS_ZO2B3R0x532bPaxXyL4
        """
        with freeze_time("2022-01-01 00:00:00", tick=True) as frozen_datetime:
            # 1. Populate cache with valid data
            result = await self.failing_compute_after_first_call(5)
            assert result == 15
            assert self.call_count == 1

            # 2. Expire the cache. Max TTL is 120 seconds.
            frozen_datetime.tick(121.0)

            # 3. Simulate multiple sequential requests, each separated by enough
            #    time for the background update task to complete and release the lock
            num_requests = 5
            for _ in range(num_requests):
                result = await self.failing_compute_after_first_call(5)
                assert result == 15  # Stale data is always returned (correct)
                # 2x margin for event loop overhead
                await asyncio.sleep(2 * self.backend_call_duration)

            # Only the first request after expiration triggers an update; subsequent ones
            # see the extended expiration and return stale data without retrying.
            assert self.call_count == 2, (
                f"Expected 2 backend calls (1 initial + 1 failed retry), but got {self.call_count}."
            )
