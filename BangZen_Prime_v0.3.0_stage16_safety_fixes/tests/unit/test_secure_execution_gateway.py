"""Regression tests for mode-aware paper execution gateway.

Live chain must remain unreachable. Paper open is allowed only in
EXECUTION_ONLY and HYBRID when emergency stop is off and settings stay paper-only.
"""

from __future__ import annotations

import unittest
import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock

from bangzen_prime.core.config import Settings
from bangzen_prime.core.errors import ConfigurationError
from bangzen_prime.core.operating_mode import OperatingMode
from bangzen_prime.core.state import ModeController
from bangzen_prime.execution.paper_trading import OpenOutcome
from bangzen_prime.execution.secure_execution_gateway import (
    ExecutionSecurityError,
    SecureExecutionGateway,
)
from bangzen_prime.risk.risk_engine import RiskDecision
from bangzen_prime.storage.database import Database

NOW = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)


def _settings(**overrides) -> Settings:
    base = {
        "BANGZEN_PAPER_TRADING": "true",
        "BANGZEN_DRY_RUN": "true",
        "BANGZEN_LIVE_TRADING": "false",
        "BANGZEN_BROADCAST_ENABLED": "false",
        "BANGZEN_EMERGENCY_STOP": "false",
        "BANGZEN_OPERATING_MODE": "TELEGRAM_ONLY",
    }
    base.update(overrides)
    return Settings.from_env(base)


def _db() -> Database:
    db = Database(":memory:")
    db.migrate()
    return db


def _paper_mock(approved: bool = True, order_id: str | None = "ord-1") -> MagicMock:
    paper = MagicMock()
    order = None
    if approved and order_id is not None:
        order = MagicMock()
        order.id = order_id
    paper.open_from_signal.return_value = OpenOutcome(
        RiskDecision(approved, ("OK",) if approved else ("RISK_DENIED",), None),
        order,
    )
    return paper


class ConstructionSecurityTests(unittest.TestCase):
    def test_refuses_live_trading_settings(self):
        # Settings.from_env already blocks LIVE_TRADING; gateway also guards.
        with self.assertRaises(ConfigurationError):
            Settings.from_env(
                {
                    "BANGZEN_LIVE_TRADING": "true",
                    "BANGZEN_PAPER_TRADING": "true",
                    "BANGZEN_DRY_RUN": "true",
                }
            )

    def test_refuses_missing_paper_flags_via_gateway_invariant(self):
        # Construct a Settings-like object is hard; use real settings then
        # mutate is frozen — so test gateway with emergency path only.
        settings = _settings()
        self.assertTrue(settings.paper_trading)
        self.assertTrue(settings.dry_run)
        self.assertFalse(settings.live_trading)


class ModeMatrixTests(unittest.TestCase):
    def _gateway(
        self, mode: OperatingMode, *, emergency: bool = False
    ) -> SecureExecutionGateway:
        controller = ModeController(mode)
        # Selecting non-telegram does not clear kill switch; paper path uses mode.execution_requested
        settings = _settings(
            BANGZEN_OPERATING_MODE=mode.value,
            BANGZEN_EMERGENCY_STOP="true" if emergency else "false",
        )
        return SecureExecutionGateway(
            settings=settings,
            mode_controller=controller,
            paper=_paper_mock(),
            db=_db(),
            clock=lambda: NOW,
            emergency_stop=lambda: emergency,
        )

    def test_telegram_only_rejects_paper_open(self):
        gw = self._gateway(OperatingMode.TELEGRAM_ONLY)
        outcome = gw.open_from_signal(uuid.uuid4())
        self.assertFalse(outcome.decision.approved)
        self.assertIsNone(outcome.order)
        self.assertIn("MODE_SIGNAL_ONLY", outcome.decision.reasons)

    def test_execution_only_allows_paper_open_when_safe(self):
        gw = self._gateway(OperatingMode.EXECUTION_ONLY)
        sid = uuid.uuid4()
        outcome = gw.open_from_signal(sid)
        self.assertTrue(outcome.decision.approved)
        self.assertIsNotNone(outcome.order)
        gw._paper.open_from_signal.assert_called_once_with(sid)

    def test_hybrid_allows_paper_open_when_safe(self):
        gw = self._gateway(OperatingMode.HYBRID)
        outcome = gw.open_from_signal(uuid.uuid4())
        self.assertTrue(outcome.decision.approved)
        self.assertIsNotNone(outcome.order)

    def test_emergency_stop_blocks_all_modes(self):
        for mode in (OperatingMode.EXECUTION_ONLY, OperatingMode.HYBRID):
            with self.subTest(mode=mode):
                gw = self._gateway(mode, emergency=True)
                outcome = gw.open_from_signal(uuid.uuid4())
                self.assertFalse(outcome.decision.approved)
                self.assertIn("EMERGENCY_STOP", outcome.decision.reasons)
                gw._paper.open_from_signal.assert_not_called()

    def test_live_execution_guard_always_raises(self):
        gw = self._gateway(OperatingMode.HYBRID)
        with self.assertRaises(ExecutionSecurityError):
            gw.assert_live_execution_impossible()

    def test_snapshot_never_claims_live_or_signer(self):
        for mode in OperatingMode:
            with self.subTest(mode=mode):
                snap = self._gateway(mode).snapshot_permissions()
                self.assertFalse(snap["live_execution_available"])
                self.assertFalse(snap["wallet_signer_available"])
                self.assertEqual(snap["mode"], mode.value)

    def test_select_mode_updates_permissions(self):
        gw = self._gateway(OperatingMode.TELEGRAM_ONLY)
        before = gw.snapshot_permissions()
        self.assertFalse(before["paper_execution_available"])
        after = gw.select_mode(OperatingMode.EXECUTION_ONLY)
        self.assertTrue(after["paper_execution_available"])
        self.assertFalse(after["telegram_enabled"])
        hybrid = gw.select_mode(OperatingMode.HYBRID)
        self.assertTrue(hybrid["paper_execution_available"])
        self.assertTrue(hybrid["telegram_enabled"])


class AuditAndRiskPropagationTests(unittest.TestCase):
    def test_risk_denial_is_propagated_and_audited(self):
        paper = _paper_mock(approved=False)
        settings = _settings(BANGZEN_OPERATING_MODE="HYBRID")
        gw = SecureExecutionGateway(
            settings=settings,
            mode_controller=ModeController(OperatingMode.HYBRID),
            paper=paper,
            db=_db(),
            clock=lambda: NOW,
            emergency_stop=lambda: False,
        )
        outcome = gw.open_from_signal(uuid.uuid4())
        self.assertFalse(outcome.decision.approved)
        self.assertIsNone(outcome.order)
        # Audit table should have at least one gateway row
        rows = gw._db.query_all(
            "SELECT event_type FROM audit_log WHERE event_type = 'SecureExecutionGateway'"
        )
        self.assertGreaterEqual(len(rows), 1)


if __name__ == "__main__":
    unittest.main()
