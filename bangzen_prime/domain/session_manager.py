import logging
from dataclasses import dataclass
from datetime import datetime, UTC
from decimal import Decimal
from typing import Callable

logger = logging.getLogger(__name__)

SESSION_US = "US"
SESSION_ASIA = "ASIA"
SESSION_EUROPE = "EUROPE"

@dataclass(frozen=True)
class SessionReport:
    session_name: str
    aggression_multiplier: Decimal
    suggested_max_signals: int
    suggested_min_quality: int
    hour_utc: int
    reason: str

class SessionManager:
    """
    Menyesuaikan agresi trading berdasarkan sesi pasar global.
    - US Session (13:00 - 21:00 UTC): Aggressive (1.2x)
    - Asia Session (00:00 - 08:00 UTC): Conservative (0.8x)
    - Default (Europe): Standard (1.0x)
    """

    def __init__(self, clock: Callable[[], datetime]):
        self.clock = clock

    def _get_hour_utc(self) -> int:
        now = self.clock()
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        else:
            now = now.astimezone(UTC)
        return now.hour

    def get_multiplier(self, hour_utc: int | None = None) -> tuple[str, Decimal]:
        if hour_utc is None:
            hour_utc = self._get_hour_utc()

        if 13 <= hour_utc < 21:
            return SESSION_US, Decimal("1.2")
        if 0 <= hour_utc < 8:
            return SESSION_ASIA, Decimal("0.8")
        return SESSION_EUROPE, Decimal("1.0")

    def apply_to_max_signals(self, base_max_signals: int, multiplier: Decimal | None = None) -> int:
        if multiplier is None:
            _, multiplier = self.get_multiplier()
        adjusted = round(Decimal(str(base_max_signals)) * multiplier)
        return max(1, int(adjusted))

    def apply_to_min_quality(self, base_min_quality: int, multiplier: Decimal | None = None) -> int:
        if multiplier is None:
            _, multiplier = self.get_multiplier()

        if multiplier <= 0:
            return base_min_quality

        adjusted = round(Decimal(str(base_min_quality)) / multiplier)
        return max(1, min(100, int(adjusted)))

    def get_session_report(
        self,
        base_max_signals: int = 3,
        base_min_quality: int = 60
    ) -> SessionReport:
        hour = self._get_hour_utc()
        session_name, multiplier = self.get_multiplier(hour)

        max_signals = self.apply_to_max_signals(base_max_signals, multiplier)
        min_quality = self.apply_to_min_quality(base_min_quality, multiplier)

        reason = f"{session_name}_session_multiplier_{multiplier}x"

        return SessionReport(
            session_name=session_name,
            aggression_multiplier=multiplier,
            suggested_max_signals=max_signals,
            suggested_min_quality=min_quality,
            hour_utc=hour,
            reason=reason
        )
