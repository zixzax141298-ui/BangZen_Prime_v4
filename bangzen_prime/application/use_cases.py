from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from bangzen_prime.application.ai_brain import AIBrain, TradeContext
from bangzen_prime.application.indicators import mean_abs_change, rsi
from bangzen_prime.application.lifecycle import assess_token_phase
from bangzen_prime.application.phase_policy import (
    Action,
    Evidence,
    PhasePolicy,
    DEFAULT_POLICY,
)
from bangzen_prime.application.ports import (
    HolderDataPort,
    MarketDataPort,
    MarketSentimentPort,
    TokenSafetyPort,
)
from bangzen_prime.application.resilience import (
    CircuitBreaker,
    ResilienceConfig,
    ResiliencePolicy,
)
from bangzen_prime.application.scoring import score_token
from bangzen_prime.application.data_validation import validate_holder_profile
from bangzen_prime.application.token_program_evidence import BLOCKED, TokenProgramEvidenceUseCase
from bangzen_prime.domain.signals import (
    AIMode,
    PriceLevels,
    RejectReason,
    Signal,
    SignalStatus,
)
from bangzen_prime.domain.tokens import PairSnapshot, SafetyAssessment, Token
from bangzen_prime.errors import DomainError, ExternalServiceError
from bangzen_prime.infrastructure.persistence.sqlite.repositories import (
    Repositories,
    UnitOfWork,
)

logger = logging.getLogger("bangzen_prime.use_cases")

RSI_PERIOD = 14
VOLATILITY_PERIOD = 14
HISTORY_LIMIT = 50


@dataclass(frozen=True)
class ScanResult:
    mint: str
    status: str
    reasons: tuple[str, ...]
    signal_id: str | None
    score: str | None
    phase: str = "UNKNOWN"


@dataclass(frozen=True)
class SignalPolicy:
    min_liquidity_usd: Decimal
    max_risk_score: Decimal
    max_data_age_seconds: int
    min_history_points: int = 15
    min_risk_reward: Decimal = Decimal("1.5")
    min_score: Decimal = Decimal("45")
    volatility_floor_pct: Decimal = Decimal("0.25")
    volatility_cap_pct: Decimal = Decimal("12.0")
    stop_multiplier: Decimal = Decimal("2")
    target_multiplier: Decimal = Decimal("3")
    cooldown_seconds: int = 90
    max_concurrent_scans: int = 8


@dataclass(frozen=True)
class RiskGovernor:
    """Kill switch dan budget risiko global perusahaan."""

    trading_enabled: bool = True
    max_open_positions: int = 10
    max_daily_new_signals: int = 50
    max_portfolio_risk_pct: Decimal = Decimal("2.0")
    max_single_position_risk_pct: Decimal = Decimal("0.25")
    daily_loss_limit_pct: Decimal = Decimal("1.0")

    def can_accept_new_signal(
        self,
        *,
        open_positions: int,
        signals_today: int,
        portfolio_risk_pct: Decimal,
        daily_loss_pct: Decimal,
    ) -> tuple[bool, RejectReason | None]:
        if not self.trading_enabled:
            return False, RejectReason.RISK_GOVERNOR_PAUSED
        if open_positions >= self.max_open_positions:
            return False, RejectReason.RISK_GOVERNOR_PAUSED
        if signals_today >= self.max_daily_new_signals:
            return False, RejectReason.RISK_GOVERNOR_PAUSED
        if portfolio_risk_pct >= self.max_portfolio_risk_pct:
            return False, RejectReason.RISK_GOVERNOR_PAUSED
        if daily_loss_pct >= self.daily_loss_limit_pct:
            return False, RejectReason.RISK_GOVERNOR_PAUSED
        return True, None


def select_best_pair(pairs: Iterable[PairSnapshot], chain: str, mint: str) -> PairSnapshot | None:
    matching = [p for p in pairs if p.chain == chain and p.base_mint == mint]
    if not matching:
        return None
    return max(matching, key=lambda p: (p.liquidity_usd, p.volume_24h_usd, p.pair_address))


async def build_signal(*, repos: Repositories, token: Token, pair: PairSnapshot, risk_score: Decimal, policy: SignalPolicy, now: datetime) -> Signal:
    token_id, pair_id = token.id, pair.pair_id
    history = repos.prices.recent(token_id, HISTORY_LIMIT)

    reasons: list[RejectReason] = []
    if len(history) < policy.min_history_points:
        reasons.append(RejectReason.INSUFFICIENT_HISTORY)
        rsi_val = Decimal("50")
        volatility = Decimal("0")
        entry = pair.price_usd
    else:
        rsi_val = rsi(history, RSI_PERIOD)
        entry = history[-1]
        volatility = mean_abs_change(history, VOLATILITY_PERIOD)
        if volatility == 0:
            reasons.append(RejectReason.NO_VOLATILITY)

    phase = assess_token_phase(pair.pair_created_at, now)
    breakdown = score_token(
        liquidity_usd=pair.liquidity_usd, volume_24h_usd=pair.volume_24h_usd,
        risk_score=risk_score, rsi_value=rsi_val, phase=phase.phase.value
    )

    if (pair.liquidity_usd < policy.min_liquidity_usd
            and phase.phase.value not in {"UNKNOWN", "LAUNCH", "EARLY"}):
        reasons.append(RejectReason.LOW_LIQUIDITY)

    if breakdown.total < policy.min_score:
        reasons.append(RejectReason.LOW_SCORE)

    levels: PriceLevels | None = None
    if not reasons:
        try:
            levels = PriceLevels(
                entry,
                entry - policy.stop_multiplier * volatility,
                entry + policy.target_multiplier * volatility,
            )
        except DomainError:
            reasons.append(RejectReason.INVALID_LEVELS)

        if levels is not None and levels.risk_reward < policy.min_risk_reward:
            reasons.append(RejectReason.LOW_RISK_REWARD)
            levels = None

    if reasons or levels is None:
        return Signal.reject(
            token_id=token_id, pair_id=pair_id, score=breakdown.total,
            reasons=tuple(dict.fromkeys(reasons)), created_at=now
        )

    return Signal.accept(
        token_id=token_id,
        pair_id=pair_id,
        score=breakdown.total,
        confidence=breakdown.confidence,
        levels=levels,
        created_at=now,
        chain=pair.chain,
        mint=pair.base_mint,
        symbol=pair.base_symbol,
        pair_address=pair.pair_address,
        dex_id=pair.dex_id,
        market_source=pair.source,
        market_observed_at=pair.observed_at,
    )


class AuditTokenUseCase:
    """Run the authoritative token-safety port without blocking the async scan loop.

    The adapter remains responsible for provider parsing. This use case additionally
    verifies that the returned assessment belongs to the exact requested chain/mint.
    """

    def __init__(self, safety: TokenSafetyPort) -> None:
        self._safety = safety

    async def execute_async(self, chain: str, mint: str) -> SafetyAssessment:
        assessment = await asyncio.to_thread(self._safety.fetch_safety, chain, mint)
        if not isinstance(assessment, SafetyAssessment):
            raise DomainError("safety adapter returned an invalid assessment")
        if assessment.chain != chain or assessment.mint != mint:
            raise DomainError("safety assessment identity does not match request")
        return assessment


def __getattr__(name: str) -> Any:
    """Lazy export of ScanMarketUseCase to avoid circular imports with scan_market."""
    if name == "ScanMarketUseCase":
        from bangzen_prime.application.scan_market import ScanMarketUseCase as _SMC

        return _SMC
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "ScanResult",
    "SignalPolicy",
    "RiskGovernor",
    "select_best_pair",
    "build_signal",
    "AuditTokenUseCase",
    "ScanMarketUseCase",
]
