"""Unit tests for ExecutionUseCase — modes, paper, live, fail-closed simulation."""

from __future__ import annotations

import unittest
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from bangzen_prime.application.execution_use_case import (
    ExecutionPath,
    ExecutionPlan,
    ExecutionPolicy,
    ExecutionUseCase,
    TradeStatus,
)
from bangzen_prime.application.mode_controller import ModeController
from bangzen_prime.application.ports import SimulationResult
from bangzen_prime.domain.operating_mode import OperatingMode
from bangzen_prime.errors import DomainError

NOW = datetime(2026, 11, 13, 15, 0, tzinfo=timezone.utc)
SOL = "So11111111111111111111111111111111111111112"
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
TAKER = "11111111111111111111111111111111"


def plan(**kwargs: Any) -> ExecutionPlan:
    base = dict(
        input_mint=USDC,
        output_mint=SOL,
        amount_raw=1_000_000,
        taker=TAKER,
        side="BUY",
        client_order_id="cid-1",
    )
    base.update(kwargs)
    return ExecutionPlan(**base)


@dataclass
class FakeOrder:
    request_id: str
    transaction_b64: str


class FakeJupiter:
    def __init__(self, order: FakeOrder | Exception | None = None) -> None:
        self.order_calls = 0
        self.execute_calls = 0
        self._order = order or FakeOrder("req-1", "dGVzdA==")

    async def order(self, *, input_mint, output_mint, amount, taker):
        self.order_calls += 1
        if isinstance(self._order, Exception):
            raise self._order
        return self._order

    async def execute(self, *, signed_transaction_b64, request_id):
        self.execute_calls += 1
        return object()


class FakeSigner:
    def __init__(self, result: str | Exception = "c2lnbmVk") -> None:
        self.calls = 0
        self._result = result

    def sign_transaction(self, serialized_tx_base64: str) -> str:
        self.calls += 1
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


class FakeHelius:
    def __init__(
        self,
        sim: SimulationResult | Exception | None = None,
        send_result: str | Exception = "5txHashExample",
    ) -> None:
        self.sim_calls = 0
        self.send_calls = 0
        self._sim = sim if sim is not None else SimulationResult(True, None)
        self._send = send_result

    async def simulate(self, signed_transaction_b64: str) -> SimulationResult:
        self.sim_calls += 1
        if isinstance(self._sim, Exception):
            raise self._sim
        return self._sim

    async def send(self, signed_transaction_b64: str) -> str:
        self.send_calls += 1
        if isinstance(self._send, Exception):
            raise self._send
        return self._send


class FakeNotifier:
    def __init__(self) -> None:
        self.messages: list[str] = []

    async def send(self, text: str) -> None:
        self.messages.append(text)


class FakePaperFill:
    def __init__(self) -> None:
        self.calls = 0

    async def record_fill(self, plan, *, fill_price, fee, at) -> str:
        self.calls += 1
        return f"paper-{plan.client_order_id}"


class ExecutionUseCaseModeTests(unittest.IsolatedAsyncioTestCase):
    async def test_telegram_only_never_calls_adapters(self):
        jup, signer, helius = FakeJupiter(), FakeSigner(), FakeHelius()
        notifier = FakeNotifier()
        uc = ExecutionUseCase(
            mode_controller=ModeController(OperatingMode.TELEGRAM_ONLY),
            policy=ExecutionPolicy(live_enabled=True, paper_trading=True, dry_run=True),
            jupiter=jup,
            signer=signer,
            helius=helius,
            notifier=notifier,
            clock=lambda: NOW,
        )
        result = await uc.execute(plan())
        self.assertEqual(result.status, TradeStatus.NOTIFIED_ONLY)
        self.assertEqual(result.path, ExecutionPath.NONE)
        self.assertIn("MODE_SIGNAL_ONLY", result.reason_codes)
        self.assertEqual(jup.order_calls, 0)
        self.assertEqual(signer.calls, 0)
        self.assertEqual(helius.sim_calls, 0)
        self.assertEqual(helius.send_calls, 0)
        self.assertEqual(len(notifier.messages), 1)

    async def test_execution_only_paper_suppresses_notifier(self):
        notifier = FakeNotifier()
        paper = FakePaperFill()
        uc = ExecutionUseCase(
            mode_controller=ModeController(OperatingMode.EXECUTION_ONLY),
            policy=ExecutionPolicy(live_enabled=False, paper_trading=True, dry_run=True),
            notifier=notifier,
            paper_fill=paper,
            market_price_lookup=lambda _m: _coro(Decimal("2.5")),
            clock=lambda: NOW,
        )
        result = await uc.execute(plan())
        self.assertEqual(result.status, TradeStatus.PAPER_FILLED)
        self.assertEqual(result.path, ExecutionPath.PAPER)
        self.assertEqual(result.paper_fill_price, Decimal("2.5"))
        self.assertEqual(paper.calls, 1)
        self.assertEqual(notifier.messages, [])

    async def test_hybrid_paper_notifies(self):
        notifier = FakeNotifier()
        uc = ExecutionUseCase(
            mode_controller=ModeController(OperatingMode.HYBRID),
            policy=ExecutionPolicy(live_enabled=False, paper_trading=True, dry_run=True),
            notifier=notifier,
            market_price_lookup=lambda _m: _coro(Decimal("1")),
            clock=lambda: NOW,
        )
        result = await uc.execute(plan())
        self.assertEqual(result.status, TradeStatus.PAPER_FILLED)
        self.assertEqual(len(notifier.messages), 1)
        self.assertIn("PAPER_FILLED", notifier.messages[0])


class ExecutionUseCaseLiveTests(unittest.IsolatedAsyncioTestCase):
    def _live_uc(self, *, jup=None, signer=None, helius=None, mode=OperatingMode.EXECUTION_ONLY):
        return ExecutionUseCase(
            mode_controller=ModeController(mode),
            policy=ExecutionPolicy(live_enabled=True, paper_trading=True, dry_run=True),
            jupiter=jup or FakeJupiter(),
            signer=signer or FakeSigner(),
            helius=helius or FakeHelius(),
            clock=lambda: NOW,
        )

    async def test_live_happy_path_order_sign_simulate_send(self):
        jup, signer, helius = FakeJupiter(), FakeSigner(), FakeHelius()
        uc = self._live_uc(jup=jup, signer=signer, helius=helius)
        result = await uc.execute(plan())
        self.assertEqual(result.status, TradeStatus.LIVE_FILLED)
        self.assertEqual(result.path, ExecutionPath.LIVE)
        self.assertEqual(result.tx_hash, "5txHashExample")
        self.assertEqual(result.request_id, "req-1")
        self.assertEqual(jup.order_calls, 1)
        self.assertEqual(signer.calls, 1)
        self.assertEqual(helius.sim_calls, 1)
        self.assertEqual(helius.send_calls, 1)

    async def test_simulation_failure_aborts_without_send(self):
        helius = FakeHelius(sim=SimulationResult(False, "SLIPPAGE_EXCEEDED"))
        jup, signer = FakeJupiter(), FakeSigner()
        uc = self._live_uc(jup=jup, signer=signer, helius=helius)
        result = await uc.execute(plan())
        self.assertEqual(result.status, TradeStatus.ABORTED)
        self.assertIn("SIMULATION_FAILED", result.reason_codes)
        self.assertIn("SLIPPAGE_EXCEEDED", result.reason_codes)
        self.assertEqual(helius.sim_calls, 1)
        self.assertEqual(helius.send_calls, 0)
        self.assertIsNone(result.tx_hash)

    async def test_simulation_exception_aborts_without_send(self):
        helius = FakeHelius(sim=RuntimeError("rpc down"))
        uc = self._live_uc(helius=helius)
        result = await uc.execute(plan())
        self.assertEqual(result.status, TradeStatus.ABORTED)
        self.assertIn("SIMULATION_ERROR", result.reason_codes)
        self.assertEqual(helius.send_calls, 0)

    async def test_sign_failure_never_simulates_or_sends(self):
        signer = FakeSigner(result=RuntimeError("SigningDisabled"))
        helius = FakeHelius()
        uc = self._live_uc(signer=signer, helius=helius)
        result = await uc.execute(plan())
        self.assertEqual(result.status, TradeStatus.REJECTED)
        self.assertIn("SIGNING_FAILED", result.reason_codes)
        self.assertEqual(helius.sim_calls, 0)
        self.assertEqual(helius.send_calls, 0)

    async def test_missing_live_adapters_rejected(self):
        uc = ExecutionUseCase(
            mode_controller=ModeController(OperatingMode.HYBRID),
            policy=ExecutionPolicy(live_enabled=True),
            clock=lambda: NOW,
        )
        result = await uc.execute(plan())
        self.assertEqual(result.status, TradeStatus.REJECTED)
        self.assertIn("LIVE_ADAPTERS_MISSING", result.reason_codes)

    async def test_emergency_stop_blocks_live(self):
        jup, signer, helius = FakeJupiter(), FakeSigner(), FakeHelius()
        uc = ExecutionUseCase(
            mode_controller=ModeController(OperatingMode.HYBRID),
            policy=ExecutionPolicy(live_enabled=True, emergency_stop=True),
            jupiter=jup,
            signer=signer,
            helius=helius,
            clock=lambda: NOW,
        )
        result = await uc.execute(plan())
        self.assertEqual(result.status, TradeStatus.REJECTED)
        self.assertIn("EMERGENCY_STOP", result.reason_codes)
        self.assertEqual(jup.order_calls, 0)


class ExecutionPlanValidationTests(unittest.TestCase):
    def test_rejects_same_mint(self):
        with self.assertRaises(DomainError):
            plan(output_mint=USDC, input_mint=USDC)

    def test_rejects_non_positive_amount(self):
        with self.assertRaises(DomainError):
            plan(amount_raw=0)


def _coro(value):
    async def _inner(*_a, **_k):
        return value

    return _inner()


# market_price_lookup expects Awaitable — fix helper for lambda usage
async def _price(_mint: str) -> Decimal:
    return Decimal("2.5")


# Re-bind tests that used broken lambda — patch module level for clarity
class PaperPriceTests(unittest.IsolatedAsyncioTestCase):
    async def test_paper_uses_lookup(self):
        uc = ExecutionUseCase(
            mode_controller=ModeController(OperatingMode.EXECUTION_ONLY),
            policy=ExecutionPolicy(live_enabled=False, paper_trading=True, dry_run=True),
            market_price_lookup=_price,
            clock=lambda: NOW,
        )
        result = await uc.execute(plan())
        self.assertEqual(result.paper_fill_price, Decimal("2.5"))
        self.assertEqual(result.status, TradeStatus.PAPER_FILLED)


if __name__ == "__main__":
    unittest.main()


class NetworkRetryTests(unittest.IsolatedAsyncioTestCase):
    """ExecutionUseCase retries transient network errors on live path."""

    async def test_jupiter_retries_then_succeeds(self):
        from bangzen_prime.errors import ExternalServiceError
        from bangzen_prime.infrastructure.resilience.policies import RetryPolicy

        class FlakyJupiter(FakeJupiter):
            def __init__(self):
                super().__init__()
                self._n = 0

            async def order(self, **kwargs):
                self._n += 1
                self.order_calls += 1
                if self._n < 3:
                    raise ExternalServiceError(
                        "timeout", service="jupiter", retryable=True, status=503
                    )
                return FakeOrder("req-retry", "dGVzdA==")

        jup = FlakyJupiter()
        sleeps: list[float] = []

        async def sleep(d: float) -> None:
            sleeps.append(d)

        uc = ExecutionUseCase(
            mode_controller=ModeController(OperatingMode.EXECUTION_ONLY),
            policy=ExecutionPolicy(live_enabled=True),
            jupiter=jup,
            signer=FakeSigner(),
            helius=FakeHelius(),
            clock=lambda: NOW,
            network_retry=RetryPolicy(max_attempts=3, base_delay_seconds=0.25, max_delay_seconds=4),
            async_sleep=sleep,
        )
        result = await uc.execute(plan())
        self.assertEqual(result.status, TradeStatus.LIVE_FILLED)
        self.assertEqual(jup.order_calls, 3)
        self.assertEqual(len(sleeps), 2)

    async def test_non_retryable_jupiter_error_not_retried(self):
        from bangzen_prime.errors import ExternalServiceError
        from bangzen_prime.infrastructure.resilience.policies import RetryPolicy

        class BadJupiter(FakeJupiter):
            async def order(self, **kwargs):
                self.order_calls += 1
                raise ExternalServiceError(
                    "bad request", service="jupiter", retryable=False, status=400
                )

        jup = BadJupiter()
        uc = ExecutionUseCase(
            mode_controller=ModeController(OperatingMode.EXECUTION_ONLY),
            policy=ExecutionPolicy(live_enabled=True),
            jupiter=jup,
            signer=FakeSigner(),
            helius=FakeHelius(),
            clock=lambda: NOW,
            network_retry=RetryPolicy(max_attempts=5),
            async_sleep=lambda _d: _async_noop(),
        )
        result = await uc.execute(plan())
        self.assertEqual(result.status, TradeStatus.REJECTED)
        self.assertEqual(jup.order_calls, 1)

    async def test_simulate_network_retry_then_business_failure_still_aborts_without_send(self):
        from bangzen_prime.errors import ExternalServiceError
        from bangzen_prime.infrastructure.resilience.policies import RetryPolicy

        class FlakySimHelius(FakeHelius):
            def __init__(self):
                super().__init__(sim=SimulationResult(False, "SLIPPAGE"))
                self._n = 0

            async def simulate(self, signed_transaction_b64: str):
                self._n += 1
                self.sim_calls += 1
                if self._n == 1:
                    raise ExternalServiceError(
                        "timeout", service="helius", retryable=True, status=504
                    )
                return SimulationResult(False, "SLIPPAGE")

        helius = FlakySimHelius()
        uc = ExecutionUseCase(
            mode_controller=ModeController(OperatingMode.EXECUTION_ONLY),
            policy=ExecutionPolicy(live_enabled=True),
            jupiter=FakeJupiter(),
            signer=FakeSigner(),
            helius=helius,
            clock=lambda: NOW,
            network_retry=RetryPolicy(max_attempts=3, base_delay_seconds=0.1),
            async_sleep=lambda _d: _async_noop(),
        )
        result = await uc.execute(plan())
        self.assertEqual(result.status, TradeStatus.ABORTED)
        self.assertIn("SIMULATION_FAILED", result.reason_codes)
        self.assertEqual(helius.sim_calls, 2)
        self.assertEqual(helius.send_calls, 0)


async def _async_noop() -> None:
    return None
