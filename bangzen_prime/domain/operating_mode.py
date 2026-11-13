"""Pure operating-mode contract for signal and execution separation.

This module never loads wallet material and never authorizes live execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class OperatingMode(str, Enum):
    """User-facing operating modes; execution remains independently locked."""

    TELEGRAM_ONLY = "TELEGRAM_ONLY"
    EXECUTION_ONLY = "EXECUTION_ONLY"
    HYBRID = "HYBRID"

    @property
    def telegram_enabled(self) -> bool:
        return self in (OperatingMode.TELEGRAM_ONLY, OperatingMode.HYBRID)

    @property
    def execution_requested(self) -> bool:
        return self in (OperatingMode.EXECUTION_ONLY, OperatingMode.HYBRID)


@dataclass(frozen=True)
class ModeSnapshot:
    """Effective permissions, not merely the user's requested mode."""

    mode: OperatingMode
    telegram_enabled: bool
    execution_requested: bool
    execution_available: bool
    wallet_access_allowed: bool
    kill_switch_engaged: bool
    reason_codes: tuple[str, ...]


def evaluate_mode(
    mode: OperatingMode,
    *,
    kill_switch_engaged: bool,
    live_execution_enabled: bool = False,
) -> ModeSnapshot:
    """Resolve requested mode into fail-closed effective permissions.

    The release default is deliberately locked. A future live-execution PR must
    change the governing constitution and pass its separate security review.
    """
    if not isinstance(mode, OperatingMode):
        raise TypeError("mode must be an OperatingMode")
    if not isinstance(kill_switch_engaged, bool):
        raise TypeError("kill_switch_engaged must be bool")
    if not isinstance(live_execution_enabled, bool):
        raise TypeError("live_execution_enabled must be bool")

    reasons: list[str] = []
    if not mode.execution_requested:
        reasons.append("EXECUTION_NOT_REQUESTED")
    if kill_switch_engaged:
        reasons.append("EXECUTION_KILL_SWITCH_ENGAGED")
    if not live_execution_enabled:
        reasons.append("LIVE_EXECUTION_DISABLED_BY_POLICY")

    execution_available = (
        mode.execution_requested
        and not kill_switch_engaged
        and live_execution_enabled
    )
    return ModeSnapshot(
        mode=mode,
        telegram_enabled=mode.telegram_enabled,
        execution_requested=mode.execution_requested,
        execution_available=execution_available,
        wallet_access_allowed=execution_available,
        kill_switch_engaged=kill_switch_engaged,
        reason_codes=tuple(reasons),
    )
