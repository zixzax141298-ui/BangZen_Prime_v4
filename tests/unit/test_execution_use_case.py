"""Unit tests for ExecutionUseCase — modes, paper, live, fail-closed simulation."""

from __future__ import annotations

import unittest
from dataclasses import dataclass
from datetime import UTC, datetime
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

NOW = datetime(2026, 11, 13, 15, 0, tzinfo=UTC)
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
        self.assertEqual(len(notifier.messages), 1)

    async def test_execution_only_paper_suppresses_notifier(self):
        notifier = FakeNotifier()
        paper = FakePaperFill()
        uc = ExecutionUseCase(
            mode_controller=ModeController(OperatingMode.EXECUTION_ONLY),
            policy=ExecutionPolicy(
                live_enabled=False, paper_trading=True, dry_run=True
            ),
            notifier=notifier,
            paper_fill=paper,
            market_price_lookup=lambda _m: _coro(Decimal("2.5")),
            clock=lambda: NOW,
        )
        result = await uc.execute(plan())
        self.assertEqual(result.status, TradeStatus.PAPER_FILLED)
        self.assertEqual(result.paper_fill_price, Decimal("2.5"))
        self.assertEqual(notifier.messages, [])

    async def test_hybrid_paper_notifies(self):
        notifier = FakeNotifier()
        uc = ExecutionUseCase(
            mode_controller=ModeController(OperatingMode.HYBRID),
            policy=ExecutionPolicy(
                live_enabled=False, paper_trading=True, dry_run=True
            ),
            notifier=notifier,
            market_price_lookup=lambda _m: _coro(Decimal(1)),
            clock=lambda: NOW,
        )
        result = await uc.execute(plan())
        self.assertEqual(result.status, TradeStatus.PAPER_FILLED)
        self.assertIn("PAPER_FILLED", notifier.messages[0])


class ExecutionUseCaseLiveTests(unittest.IsolatedAsyncioTestCase):
    def _live_uc(
        self, *, jup=None, signer=None, helius=None, mode=OperatingMode.EXECUTION_ONLY
    ):
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
        self.assertEqual(result.tx_hash, "5txHashExample")

    async def test_simulation_failure_aborts_without_send(self):
        helius = FakeHelius(sim=SimulationResult(False, "SLIPPAGE_EXCEEDED"))
        uc = self._live_uc(helius=helius)
        result = await uc.execute(plan())
        self.assertEqual(result.status, TradeStatus.ABORTED)
        self.assertIn("SLIPPAGE_EXCEEDED", result.reason_codes)
        self.assertEqual(helius.send_calls, 0)

    async def test_sign_failure_never_simulates_or_sends(self):
        signer = FakeSigner(result=RuntimeError("SigningDisabled"))
        helius = FakeHelius()
        uc = self._live_uc(signer=signer, helius=helius)
        result = await uc.execute(plan())
        self.assertEqual(result.status, TradeStatus.REJECTED)
        self.assertIn("SIGNING_FAILED", result.reason_codes)
        self.assertEqual(helius.sim_calls, 0)

    async def test_emergency_stop_blocks_live(self):
        jup = FakeJupiter()
        uc = ExecutionUseCase(
            mode_controller=ModeController(OperatingMode.HYBRID),
            policy=ExecutionPolicy(live_enabled=True, emergency_stop=True),
            jupiter=jup,
            clock=lambda: NOW,
        )
        result = await uc.execute(plan())
        self.assertEqual(result.status, TradeStatus.REJECTED)
        self.assertIn("EMERGENCY_STOP", result.reason_codes)
        self.assertEqual(jup.order_calls, 0)


def _coro(value):
    async def _inner(*_a, **_k):
        return value

    return _inner()
