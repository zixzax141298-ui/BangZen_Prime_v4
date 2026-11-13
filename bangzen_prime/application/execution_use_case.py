"""Execution orchestration use case (paper + live paths).

Clean Architecture application service. Adapters are injected; this module does
not construct wallets, load private keys, or open network clients.

Fail-closed rules:
  - TELEGRAM_ONLY: notify only (if notifier present); never trade.
  - EXECUTION_ONLY / HYBRID: may trade paper or live per policy flags.
  - Live path requires: mode requests execution, live_enabled policy, successful
    Jupiter order, successful sign, successful Helius.simulate, then send.
  - Any simulation failure aborts before send.
  - Paper path never calls Jupiter, signer, or Helius.

Real release adapters (WalletSigner, HeliusRpc.send) remain locked; this use case
is the orchestration layer for when an audited signer/broadcast stack is injected.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Protocol

from bangzen_prime.application.mode_controller import ModeController
from bangzen_prime.application.ports import SimulationResult
from bangzen_prime.domain.operating_mode import OperatingMode
from bangzen_prime.domain.tokens import validate_mint
from bangzen_prime.errors import DomainError, ExternalServiceError
from bangzen_prime.infrastructure.resilience.async_retry import async_retry
from bangzen_prime.infrastructure.resilience.policies import RetryPolicy

logger = logging.getLogger("bangzen_prime.execution_use_case")


# ---------------------------------------------------------------------------
# Domain / application contracts
# ---------------------------------------------------------------------------


class TradeStatus(str, Enum):
    NOTIFIED_ONLY = "NOTIFIED_ONLY"
    PAPER_FILLED = "PAPER_FILLED"
    LIVE_FILLED = "LIVE_FILLED"
    REJECTED = "REJECTED"
    ABORTED = "ABORTED"


class ExecutionPath(str, Enum):
    NONE = "NONE"
    PAPER = "PAPER"
    LIVE = "LIVE"


@dataclass(frozen=True)
class ExecutionPlan:
    """Intent to exchange input_mint -> output_mint for amount_raw atomic units."""

    input_mint: str
    output_mint: str
    amount_raw: int
    taker: str
    side: str = "BUY"  # informational: BUY | SELL
    client_order_id: str | None = None

    def __post_init__(self) -> None:
        validate_mint(self.input_mint)
        validate_mint(self.output_mint)
        validate_mint(self.taker)
        if self.input_mint == self.output_mint:
            raise DomainError("input and output mint must differ")
        if isinstance(self.amount_raw, bool) or not isinstance(self.amount_raw, int):
            raise DomainError("amount_raw must be an int")
        if self.amount_raw <= 0:
            raise DomainError("amount_raw must be positive")
        if self.side not in {"BUY", "SELL"}:
            raise DomainError("side must be BUY or SELL")


@dataclass(frozen=True)
class TradeResult:
    status: TradeStatus
    path: ExecutionPath
    reason_codes: tuple[str, ...]
    tx_hash: str | None = None
    request_id: str | None = None
    paper_fill_price: Decimal | None = None
    paper_fee: Decimal | None = None
    client_order_id: str | None = None
    mode: OperatingMode | None = None

    @property
    def ok(self) -> bool:
        return self.status in {
            TradeStatus.NOTIFIED_ONLY,
            TradeStatus.PAPER_FILLED,
            TradeStatus.LIVE_FILLED,
        }


@dataclass(frozen=True)
class ExecutionPolicy:
    """Explicit policy flags independent of Settings locks (inject in production)."""

    paper_trading: bool = True
    dry_run: bool = True
    live_enabled: bool = False  # must be explicitly True for live path
    emergency_stop: bool = False


# ---------------------------------------------------------------------------
# Ports (async) — adapters may wrap sync implementations with to_thread
# ---------------------------------------------------------------------------


class JupiterOrderPort(Protocol):
    async def order(
        self, *, input_mint: str, output_mint: str, amount: int, taker: str
    ) -> Any:
        """Return an object with request_id and transaction_b64."""
        ...

    async def execute(self, *, signed_transaction_b64: str, request_id: str) -> Any:
        """Optional Jupiter /execute path; not required if Helius.send is used."""
        ...


class WalletSignerPort(Protocol):
    def sign_transaction(self, serialized_tx_base64: str) -> str: ...


class HeliusExecutionPort(Protocol):
    async def simulate(self, signed_transaction_b64: str) -> SimulationResult: ...

    async def send(self, signed_transaction_b64: str) -> str:
        """Return transaction signature / hash."""
        ...


class NotifierPort(Protocol):
    async def send(self, text: str) -> None: ...


class PaperFillPort(Protocol):
    async def record_fill(
        self,
        plan: ExecutionPlan,
        *,
        fill_price: Decimal,
        fee: Decimal,
        at: datetime,
    ) -> str:
        """Persist paper fill; return paper order id."""
        ...


# ---------------------------------------------------------------------------
# Use case
# ---------------------------------------------------------------------------


class ExecutionUseCase:
    """Orchestrates paper/live trades under operating mode + fail-closed gates."""

    def __init__(
        self,
        *,
        mode_controller: ModeController,
        policy: ExecutionPolicy,
        jupiter: JupiterOrderPort | None = None,
        signer: WalletSignerPort | None = None,
        helius: HeliusExecutionPort | None = None,
        notifier: NotifierPort | None = None,
        paper_fill: PaperFillPort | None = None,
        market_price_lookup: Callable[[str], Awaitable[Decimal]] | None = None,
        fee_rate: Decimal = Decimal("0.003"),
        clock: Callable[[], datetime] | None = None,
        network_retry: RetryPolicy | None = None,
        async_sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        self._mode = mode_controller
        self._policy = policy
        self._jupiter = jupiter
        self._signer = signer
        self._helius = helius
        self._notifier = notifier
        self._paper_fill = paper_fill
        self._market_price_lookup = market_price_lookup
        self._fee_rate = fee_rate
        self._clock = clock or (lambda: datetime.now(UTC))
        self._network_retry = network_retry or RetryPolicy(
            max_attempts=3, base_delay_seconds=0.5, max_delay_seconds=8.0
        )
        self._async_sleep = async_sleep
        if fee_rate < 0 or fee_rate > Decimal("0.1"):
            raise DomainError("fee_rate out of allowed range")

    async def execute(self, plan: ExecutionPlan) -> TradeResult:
        if not isinstance(plan, ExecutionPlan):
            raise DomainError("plan must be ExecutionPlan")

        mode_state = self._mode.snapshot()
        mode = mode_state.mode
        now = self._clock()
        order_id = plan.client_order_id or str(uuid.uuid4())

        if self._policy.emergency_stop:
            return self._reject(mode, order_id, ExecutionPath.NONE, ("EMERGENCY_STOP",))

        # --- TELEGRAM_ONLY: notify, never execute ---
        if mode is OperatingMode.TELEGRAM_ONLY:
            await self._notify_if_allowed(
                mode_state.telegram_enabled,
                self._format_signal_only(plan, order_id),
            )
            return TradeResult(
                status=TradeStatus.NOTIFIED_ONLY,
                path=ExecutionPath.NONE,
                reason_codes=("MODE_SIGNAL_ONLY",),
                client_order_id=order_id,
                mode=mode,
            )

        if not mode.execution_requested:
            return self._reject(
                mode, order_id, ExecutionPath.NONE, ("EXECUTION_NOT_REQUESTED",)
            )

        # Resolve path: live only when explicitly enabled; else paper when paper flags set
        path = self._resolve_path()
        if path is ExecutionPath.NONE:
            return self._reject(
                mode,
                order_id,
                ExecutionPath.NONE,
                ("NO_EXECUTABLE_PATH", "LIVE_DISABLED_AND_PAPER_DISABLED"),
            )

        if path is ExecutionPath.PAPER:
            result = await self._execute_paper(plan, mode, order_id, now)
        else:
            result = await self._execute_live(plan, mode, order_id)

        # HYBRID notifies on outcome; EXECUTION_ONLY suppresses
        if mode is OperatingMode.HYBRID and mode_state.telegram_enabled:
            await self._notify_if_allowed(
                True,
                self._format_execution_notice(plan, result),
            )
        return result

    def _resolve_path(self) -> ExecutionPath:
        if self._policy.live_enabled:
            return ExecutionPath.LIVE
        if self._policy.paper_trading and self._policy.dry_run:
            return ExecutionPath.PAPER
        return ExecutionPath.NONE

    async def _execute_paper(
        self,
        plan: ExecutionPlan,
        mode: OperatingMode,
        order_id: str,
        now: datetime,
    ) -> TradeResult:
        price = Decimal(1)
        if self._market_price_lookup is not None:
            try:
                price = await self._market_price_lookup(plan.output_mint)
            except Exception as exc:  # noqa: BLE001 — fail closed
                logger.warning("paper price lookup failed: %s", type(exc).__name__)
                return self._reject(
                    mode, order_id, ExecutionPath.PAPER, ("MARKET_PRICE_UNAVAILABLE",)
                )
        if price <= 0:
            return self._reject(
                mode, order_id, ExecutionPath.PAPER, ("INVALID_MARKET_PRICE",)
            )

        notional = Decimal(plan.amount_raw) * price
        fee = (notional * self._fee_rate).quantize(Decimal("0.00000001"))

        paper_id = order_id
        if self._paper_fill is not None:
            try:
                paper_id = await self._paper_fill.record_fill(
                    plan, fill_price=price, fee=fee, at=now
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("paper fill persist failed: %s", type(exc).__name__)
                return self._reject(
                    mode, order_id, ExecutionPath.PAPER, ("PAPER_PERSIST_FAILED",)
                )

        return TradeResult(
            status=TradeStatus.PAPER_FILLED,
            path=ExecutionPath.PAPER,
            reason_codes=("PAPER_FILL",),
            paper_fill_price=price,
            paper_fee=fee,
            client_order_id=paper_id,
            mode=mode,
        )

    async def _execute_live(
        self,
        plan: ExecutionPlan,
        mode: OperatingMode,
        order_id: str,
    ) -> TradeResult:
        if self._jupiter is None or self._signer is None or self._helius is None:
            return self._reject(
                mode,
                order_id,
                ExecutionPath.LIVE,
                ("LIVE_ADAPTERS_MISSING",),
            )

        # Step 1: Jupiter unsigned order (retry transient network failures)
        try:
            order = await async_retry(
                lambda: self._jupiter.order(
                    input_mint=plan.input_mint,
                    output_mint=plan.output_mint,
                    amount=plan.amount_raw,
                    taker=plan.taker,
                ),
                policy=self._network_retry,
                sleep=self._async_sleep,
                operation_name="jupiter.order",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("jupiter order failed: %s", type(exc).__name__)
            reason = (
                "JUPITER_ORDER_NETWORK_EXHAUSTED"
                if isinstance(exc, ExternalServiceError) and exc.retryable
                else "JUPITER_ORDER_FAILED"
            )
            return self._reject(
                mode, order_id, ExecutionPath.LIVE, (reason, type(exc).__name__)
            )

        request_id = getattr(order, "request_id", None)
        tx_b64 = getattr(order, "transaction_b64", None)
        if not request_id or not tx_b64:
            return self._reject(
                mode, order_id, ExecutionPath.LIVE, ("JUPITER_ORDER_MALFORMED",)
            )

        # Step 2: Sign
        try:
            signed_b64 = self._signer.sign_transaction(tx_b64)
        except Exception as exc:  # noqa: BLE001
            logger.warning("sign failed: %s", type(exc).__name__)
            return self._reject(
                mode,
                order_id,
                ExecutionPath.LIVE,
                ("SIGNING_FAILED", type(exc).__name__),
            )
        if not isinstance(signed_b64, str) or not signed_b64.strip():
            return self._reject(
                mode, order_id, ExecutionPath.LIVE, ("SIGNING_EMPTY_RESULT",)
            )

        # Step 3: CRITICAL — simulate with network retries; business sim failure aborts
        try:
            sim = await async_retry(
                lambda: self._helius.simulate(signed_b64),
                policy=self._network_retry,
                sleep=self._async_sleep,
                operation_name="helius.simulate",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("simulate raised: %s", type(exc).__name__)
            return TradeResult(
                status=TradeStatus.ABORTED,
                path=ExecutionPath.LIVE,
                reason_codes=("SIMULATION_ERROR", type(exc).__name__),
                request_id=str(request_id),
                client_order_id=order_id,
                mode=mode,
            )
        if not isinstance(sim, SimulationResult) or not sim.ok:
            code = (
                sim.error_code if isinstance(sim, SimulationResult) else "SIM_INVALID"
            )
            return TradeResult(
                status=TradeStatus.ABORTED,
                path=ExecutionPath.LIVE,
                reason_codes=("SIMULATION_FAILED", code or "UNKNOWN"),
                request_id=str(request_id),
                client_order_id=order_id,
                mode=mode,
            )

        # Step 4: Broadcast only after clean simulation (retry retryable network only)
        try:
            tx_hash = await async_retry(
                lambda: self._helius.send(signed_b64),
                policy=self._network_retry,
                sleep=self._async_sleep,
                operation_name="helius.send",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("send failed: %s", type(exc).__name__)
            reason = (
                "BROADCAST_NETWORK_EXHAUSTED"
                if isinstance(exc, ExternalServiceError) and exc.retryable
                else "BROADCAST_FAILED"
            )
            return self._reject(
                mode,
                order_id,
                ExecutionPath.LIVE,
                (reason, type(exc).__name__),
                request_id=str(request_id),
            )
        if not isinstance(tx_hash, str) or not tx_hash.strip():
            return self._reject(
                mode,
                order_id,
                ExecutionPath.LIVE,
                ("BROADCAST_EMPTY_SIGNATURE",),
                request_id=str(request_id),
            )

        return TradeResult(
            status=TradeStatus.LIVE_FILLED,
            path=ExecutionPath.LIVE,
            reason_codes=("LIVE_SENT",),
            tx_hash=tx_hash.strip(),
            request_id=str(request_id),
            client_order_id=order_id,
            mode=mode,
        )

    def _reject(
        self,
        mode: OperatingMode,
        order_id: str,
        path: ExecutionPath,
        reasons: tuple[str, ...],
        request_id: str | None = None,
    ) -> TradeResult:
        return TradeResult(
            status=TradeStatus.REJECTED,
            path=path,
            reason_codes=reasons,
            request_id=request_id,
            client_order_id=order_id,
            mode=mode,
        )

    async def _notify_if_allowed(self, enabled: bool, text: str) -> None:
        if not enabled or self._notifier is None:
            return
        try:
            await self._notifier.send(text)
        except Exception as exc:  # noqa: BLE001
            logger.warning("notifier failed: %s", type(exc).__name__)

    @staticmethod
    def _format_signal_only(plan: ExecutionPlan, order_id: str) -> str:
        return (
            "[SIGNAL ONLY | NO EXECUTION]\n"
            f"side={plan.side} in={plan.input_mint} out={plan.output_mint}\n"
            f"amount_raw={plan.amount_raw} ref={order_id}"
        )

    @staticmethod
    def _format_execution_notice(plan: ExecutionPlan, result: TradeResult) -> str:
        return (
            f"[EXECUTION {result.status.value} | {result.path.value}]\n"
            f"side={plan.side} reasons={','.join(result.reason_codes)}\n"
            f"tx={result.tx_hash or '-'} ref={result.client_order_id}"
        )
