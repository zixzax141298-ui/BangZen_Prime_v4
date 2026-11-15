"""Application-level operating-mode controller.

The controller selects signal/notification behavior and exposes an execution
veto. It intentionally has no signer, wallet, RPC, or transaction dependency.
"""

from __future__ import annotations

import threading

from bangzen_prime.core.operating_mode import (
    ModeSnapshot,
    OperatingMode,
    evaluate_mode,
)


class ModeController:
    """Thread-safe in-process mode controller with a latched kill switch."""

    def __init__(self, mode: OperatingMode = OperatingMode.TELEGRAM_ONLY) -> None:
        if not isinstance(mode, OperatingMode):
            raise TypeError("mode must be an OperatingMode")
        self._lock = threading.RLock()
        self._mode = mode
        # Safe by default. This PR intentionally provides no disarm operation.
        self._kill_switch_engaged = True

    def snapshot(self) -> ModeSnapshot:
        with self._lock:
            return evaluate_mode(
                self._mode,
                kill_switch_engaged=self._kill_switch_engaged,
                live_execution_enabled=False,
            )

    def select_mode(self, mode: OperatingMode) -> ModeSnapshot:
        """Select a user-facing mode without granting execution authority."""
        if not isinstance(mode, OperatingMode):
            raise TypeError("mode must be an OperatingMode")
        with self._lock:
            self._mode = mode
            if mode is OperatingMode.TELEGRAM_ONLY:
                self._kill_switch_engaged = True
            return self.snapshot()

    def engage_kill_switch(self) -> ModeSnapshot:
        """Latch the execution stop; no reset API exists in this release."""
        with self._lock:
            self._kill_switch_engaged = True
            return self.snapshot()

    def assert_execution_permitted(self) -> None:
        """Raise unless the effective policy permits execution (always denied here)."""
        state = self.snapshot()
        if not state.execution_available or not state.wallet_access_allowed:
            reasons = ",".join(state.reason_codes) or "EXECUTION_NOT_AUTHORIZED"
            raise PermissionError(f"execution denied: {reasons}")
