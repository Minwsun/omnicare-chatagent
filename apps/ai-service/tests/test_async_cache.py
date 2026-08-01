import asyncio
import unittest

from app.async_cache import AsyncSingleFlightCache


class AsyncSingleFlightCacheTests(unittest.IsolatedAsyncioTestCase):
    async def test_reuses_cached_value(self):
        cache = AsyncSingleFlightCache(ttl_seconds=60, max_entries=10)
        calls = 0

        async def compute():
            nonlocal calls
            calls += 1
            return "value"

        first, first_hit = await cache.get_or_compute("key", compute)
        second, second_hit = await cache.get_or_compute("key", compute)

        self.assertEqual((first, second), ("value", "value"))
        self.assertFalse(first_hit)
        self.assertTrue(second_hit)
        self.assertEqual(calls, 1)

    async def test_coalesces_concurrent_computation(self):
        cache = AsyncSingleFlightCache(ttl_seconds=60, max_entries=10)
        calls = 0

        async def compute():
            nonlocal calls
            calls += 1
            await asyncio.sleep(0.01)
            return "value"

        results = await asyncio.gather(*(cache.get_or_compute("key", compute) for _ in range(5)))

        self.assertTrue(all(value == "value" for value, _ in results))
        self.assertEqual(calls, 1)

    async def test_clear_invalidates_entries(self):
        cache = AsyncSingleFlightCache(ttl_seconds=60, max_entries=10)
        calls = 0

        async def compute():
            nonlocal calls
            calls += 1
            return calls

        first, _ = await cache.get_or_compute("key", compute)
        await cache.clear()
        second, hit = await cache.get_or_compute("key", compute)

        self.assertEqual((first, second), (1, 2))
        self.assertFalse(hit)


if __name__ == "__main__":
    unittest.main()
