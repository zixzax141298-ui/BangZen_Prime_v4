"""Mode-aware paper execution gateway with fail-closed multi-layer security.

Three user-facing modes (already in domain.operating_mode):

  TELEGRAM_ONLY   — signal alerts only; paper open/close denied
  EXECUTION_ONLY  — paper buy/sell allowed; Telegram suppressed upstream
  HYBRID          — paper buy/sell + Telegram alerts

Live chain signing/broadcast remains permanently locked in this release.
This gateway never accepts private keys, never builds signed transactions,
and never calls RPC broadcast. All fills go through SimulatedExecution only.

Security layers (all must pass for a paper open):
  1. Settings invariants: paper_trading + dry_run, live/broadcast off
  2. Operating mode requests execution (EXECUTION_ONLY or HYBRID)
  3. Emergency stop not engaged
  4. Mode kill-switch does not block *paper* path (live still blocked by policy)
  5. RiskEngine independent veto + sizing
  6. Optional AI advisory gate (can only deny, never force-approve)
  7. Exposure reservation + idempotent order key
  8. Full audit of every allow/deny decision
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from bangzen_prime.application.mode_controller import ModeController
from bangzen_prime.application.paper_trading import OpenOutcome, PaperTradingUseCase
from bangzen_prime.application.risk_engine import RiskDecision
from bangzen_prime.domain.operating_mode import OperatingMode
from bangzen_prime.errors import ConfigurationError
from bangzen_prime.infrastructure.persistence.sqlite.database import Database
from bangzen_prime.infrastructure.persistence.sqlite.outbox import AuditLog
from bangzen_prime.settings import Settings


class ExecutionSecurityError(PermissionError):
    """Raised when a security layer blocks paper or live execution."""


@dataclass(frozen=True)
class GatewayDecision:
    """Immutable record of a mode-aware execution decision."""

    allowed: bool
    mode: OperatingMode
    action: str  # OPEN | CLOSE | REJECT
    reason_codes: tuple[str, ...]
    signal_id: str | None
    order_id: str | None
    decided_at: datetime

    def as_audit_payload(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "mode": self.mode.value,
            "action": self.action,
            "reason_codes": list(self.reason_codes),
            "signal_id": self.signal_id,
            "order_id": self.order_id,
            "decided_at": self.decided_at.isoformat(),
            "live_execution": False,
        }


class SecureExecutionGateway:
    """Single entry point for mode-gated paper buy/sell.

    Live path is structurally unreachable: settings validation + hardcoded
    live_execution_enabled=False in ModeController + this class never
    constructs a signer or broadcaster.
    """

    def __init__(
        self,
        *,
        settings: Settings,
        mode_controller: ModeController,
        paper: PaperTradingUseCase,
        db: Database,
        clock: Callable[[], datetime] | None = None,
        emergency_stop: Callable[[], bool] | None = None,
    ) -> None:
        self._settings = settings
        self._mode = mode_controller
        self._paper = paper
        self._db = db
        self._clock = clock or (lambda: datetime.now(UTC))
        self._emergency_stop = emergency_stop or (lambda: bool(settings.emergency_stop))
        self._lock = threading.RLock()
        self._assert_settings_locked_to_paper()

    def _assert_settings_locked_to_paper(self) -> None:
        """Hard invariants — fail process construction if violated."""
        s = self._settings
        if not s.paper_trading or not s.dry_run:
            raise ConfigurationError(
                "SecureExecutionGateway requires paper_trading=true and dry_run=true"
            )
        if s.live_trading:
            raise ConfigurationError("SecureExecutionGateway refuses live_trading=true")
        if s.broadcast_enabled:
            raise ConfigurationError(
                "SecureExecutionGateway refuses broadcast_enabled=true"
            )

    def snapshot_permissions(self) -> dict[str, Any]:
        """Operator-visible effective permissions (never claims live is available)."""
        state = self._mode.snapshot()
        paper_ok, reasons = self._paper_path_allowed(state.mode)
        return {
            "mode": state.mode.value,
            "telegram_enabled": state.telegram_enabled,
            "paper_execution_requested": state.execution_requested,
            "paper_execution_available": paper_ok,
            "live_execution_available": False,
            "wallet_signer_available": False,
            "kill_switch_engaged": state.kill_switch_engaged,
            "emergency_stop": self._emergency_stop(),
            "reason_codes": list(reasons) if not paper_ok else list(state.reason_codes),
        }

    def _paper_path_allowed(self, mode: OperatingMode) -> tuple[bool, tuple[str, ...]]:
        reasons: list[str] = []
        if mode is OperatingMode.TELEGRAM_ONLY:
            reasons.append("MODE_SIGNAL_ONLY")
        if not mode.execution_requested:
            reasons.append("EXECUTION_NOT_REQUESTED")
        if self._emergency_stop():
            reasons.append("EMERGENCY_STOP")
        # Settings re-checked every call (defense in depth)
        if not self._settings.paper_trading or not self._settings.dry_run:
            reasons.append("PAPER_DRY_RUN_REQUIRED")
        if self._settings.live_trading or self._settings.broadcast_enabled:
            reasons.append("LIVE_OR_BROADCAST_FLAG_SET")
        return (len(reasons) == 0, tuple(reasons))

    def _audit(self, decision: GatewayDecision) -> None:
        with self._db.transaction() as conn:
            AuditLog(conn).append(
                "SecureExecutionGateway",
                decision.as_audit_payload(),
                decision.decided_at,
            )

    def open_from_signal(self, signal_id: uuid.UUID) -> OpenOutcome:
        """Paper open gated by mode + security layers. Never touches the chain."""
        with self._lock:
            now = self._clock()
            mode = self._mode.snapshot().mode
            allowed, reasons = self._paper_path_allowed(mode)
            if not allowed:
                decision = GatewayDecision(
                    allowed=False,
                    mode=mode,
                    action="REJECT",
                    reason_codes=reasons,
                    signal_id=str(signal_id),
                    order_id=None,
                    decided_at=now,
                )
                self._audit(decision)
                return OpenOutcome(
                    RiskDecision(False, reasons, None),
                    None,
                )

            outcome = self._paper.open_from_signal(signal_id)
            order_id = outcome.order.id if outcome.order is not None else None
            gateway = GatewayDecision(
                allowed=outcome.decision.approved and outcome.order is not None,
                mode=mode,
                action="OPEN" if outcome.order is not None else "REJECT",
                reason_codes=outcome.decision.reasons
                or (
                    ("OPENED",)
                    if outcome.order is not None
                    else ("RISK_OR_SIGNAL_DENIED",)
                ),
                signal_id=str(signal_id),
                order_id=order_id,
                decided_at=now,
            )
            self._audit(gateway)
            return outcome

    def assert_live_execution_impossible(self) -> None:
        """Explicit guard for any future caller that might confuse paper with live."""
        raise ExecutionSecurityError(
            "live chain execution is permanently disabled in this release: "
            "no signer, no broadcast, no private key loading"
        )

    def select_mode(self, mode: OperatingMode) -> dict[str, Any]:
        """Change operating mode; TELEGRAM_ONLY latches live kill-switch (existing policy)."""
        self._mode.select_mode(mode)
        return self.snapshot_permissions()


def build_secure_execution_gateway(
    *,
    settings: Settings,
    mode_controller: ModeController,
    paper: PaperTradingUseCase,
    db: Database,
    clock: Callable[[], datetime] | None = None,
) -> SecureExecutionGateway:
    """Factory used by operators/tests; never enables live trading."""
    return SecureExecutionGateway(
        settings=settings,
        mode_controller=mode_controller,
        paper=paper,
        db=db,
        clock=clock,
        emergency_stop=lambda: bool(settings.emergency_stop),
    )
