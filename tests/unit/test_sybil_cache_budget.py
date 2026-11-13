from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from bangzen_prime.infrastructure.adapters.onchain.sybil_adapter import SybilAdapter


class FakeAsyncClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeRpcResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {"result": []}


class FakeRpcClient:
    def __init__(self):
        self.calls = 0

    async def post(self, *args, **kwargs):
        self.calls += 1
        return FakeRpcResponse()


class SybilCacheTests(unittest.TestCase):
    def test_determinate_wallet_observations_are_cached_until_ttl_expires(self):
        now = [100.0]
        adapter = SybilAdapter(
            "https://example.invalid", cache_ttl_seconds=10, clock=lambda: now[0]
        )
        calls = []

        async def find_funder(_client, holder):
            calls.append(holder)
            return "SELF", None

        adapter._find_funder = find_funder
        holders = ["wallet-a", "wallet-b", "wallet-c"]
        with patch(
            "bangzen_prime.infrastructure.adapters.onchain.sybil_adapter.httpx.AsyncClient",
            return_value=FakeAsyncClient(),
        ):
            first = asyncio.run(adapter.check_sybil_cluster("mint", holders))
            second = asyncio.run(adapter.check_sybil_cluster("mint", holders))

        self.assertTrue(first.available)
        self.assertTrue(second.available)
        self.assertEqual(len(calls), 3)

        now[0] += 11
        with patch(
            "bangzen_prime.infrastructure.adapters.onchain.sybil_adapter.httpx.AsyncClient",
            return_value=FakeAsyncClient(),
        ):
            third = asyncio.run(adapter.check_sybil_cluster("mint", holders))
        self.assertTrue(third.available)
        self.assertEqual(len(calls), 6)

    def test_unavailable_observations_are_not_cached(self):
        adapter = SybilAdapter("https://example.invalid")
        calls = []

        async def find_funder(_client, holder):
            calls.append(holder)
            if len(calls) <= 3:
                return "UNAVAILABLE", None
            return "SELF", None

        adapter._find_funder = find_funder
        holders = ["wallet-a", "wallet-b", "wallet-c"]
        with patch(
            "bangzen_prime.infrastructure.adapters.onchain.sybil_adapter.httpx.AsyncClient",
            return_value=FakeAsyncClient(),
        ):
            first = asyncio.run(adapter.check_sybil_cluster("mint", holders))
            second = asyncio.run(adapter.check_sybil_cluster("mint", holders))

        self.assertFalse(first.available)
        self.assertTrue(second.available)
        self.assertEqual(len(calls), 6)

    def test_concurrent_duplicate_wallet_lookups_are_coalesced(self):
        adapter = SybilAdapter("https://example.invalid")
        calls = []

        async def find_funder(_client, holder):
            calls.append(holder)
            await asyncio.sleep(0.01)
            return "SELF", None

        adapter._find_funder = find_funder

        async def run_both():
            with patch(
                "bangzen_prime.infrastructure.adapters.onchain.sybil_adapter.httpx.AsyncClient",
                return_value=FakeAsyncClient(),
            ):
                return await asyncio.gather(
                    adapter.check_sybil_cluster("mint-a", ["wallet-a", "wallet-b", "wallet-c"]),
                    adapter.check_sybil_cluster("mint-b", ["wallet-a", "wallet-b", "wallet-c"]),
                )

        first, second = asyncio.run(run_both())
        self.assertTrue(first.available)
        self.assertTrue(second.available)
        self.assertCountEqual(calls, ["wallet-a", "wallet-b", "wallet-c"])

    def test_rpc_budget_denies_calls_without_retrying_or_sleeping(self):
        now = [0.0]
        adapter = SybilAdapter(
            "https://example.invalid",
            max_rpc_calls_per_minute=1,
            clock=lambda: now[0],
        )
        client = FakeRpcClient()

        async def run():
            await adapter._rpc_call(client, "getSignaturesForAddress", ["wallet", {"limit": 20}])
            with self.assertRaisesRegex(RuntimeError, "budget_exhausted"):
                await adapter._rpc_call(client, "getSignaturesForAddress", ["wallet", {"limit": 20}])

        asyncio.run(run())
        self.assertEqual(client.calls, 1)

        now[0] = 60.0
        asyncio.run(
            adapter._rpc_call(client, "getSignaturesForAddress", ["wallet", {"limit": 20}])
        )
        self.assertEqual(client.calls, 2)


if __name__ == "__main__":
    unittest.main()
