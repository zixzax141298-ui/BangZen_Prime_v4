"""Operational risk engine. Every limit states its unit; every decision lists its reasons.

Early exits (in order): emergency stop, stale portfolio, invalid equity. Otherwise all checks
run and every failing reason is reported, so the audit trail is complete.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from bangzen_prime.core.errors import DomainError
from bangzen_prime.core.shared import ensure_utc
from bangzen_prime.core.values import non_negative, percent, positive, unit_interval
from bangzen_prime.risk.risk import PortfolioSnapshot, SizingResult, size_position
from bangzen_prime.scoring.signals import PriceLevels
from bangzen_prime.security.token_2022_extension_evidence import (
    Token2022ExtensionEvidence,
)
from bangzen_prime.security.token_2022_extensions import REJECTED
from bangzen_prime.security.token_2022_risk import evaluate_token_2022_risk
from bangzen_prime.security.token_programs import (
    SUPPORTED_TOKEN_PROGRAMS,
    TOKEN_2022_PROGRAM_ID,
    TOKEN_PROGRAM_ID,
)

ZERO = Decimal(0)


@dataclass(frozen=True)
class RiskLimits:
    max_risk_per_trade_pct: Decimal  # percent of equity (quote currency)
    max_open_positions: int  # count
    max_exposure_quote: Decimal  # quote currency, total notional of open positions
    max_drawdown_pct: Decimal  # percent of peak equity
    min_liquidity_usd: Decimal  # USD of pair liquidity
    max_spread_pct: Decimal  # percent of price
    max_slippage_pct: Decimal  # percent of price
    fee_rate: Decimal  # fraction per side
    loss_cooldown: timedelta = timedelta(hours=1)
    max_portfolio_age: timedelta = timedelta(seconds=60)
    emergency_stop: bool = False

    def __post_init__(self) -> None:
        """Reject malformed limits at construction, before they can approve a trade."""
        percent(self.max_risk_per_trade_pct, "max_risk_per_trade_pct", allow_zero=False)
        if isinstance(self.max_open_positions, bool) or not isinstance(
            self.max_open_positions, int
        ):
            raise DomainError("max_open_positions must be an integer")
        if self.max_open_positions <= 0:
            raise DomainError("max_open_positions must be positive")
        positive(self.max_exposure_quote, "max_exposure_quote")
        percent(self.max_drawdown_pct, "max_drawdown_pct")
        non_negative(self.min_liquidity_usd, "min_liquidity_usd")
        percent(self.max_spread_pct, "max_spread_pct")
        percent(self.max_slippage_pct, "max_slippage_pct")
        unit_interval(self.fee_rate, "fee_rate")
        if not isinstance(
            self.loss_cooldown, timedelta
        ) or self.loss_cooldown < timedelta(0):
            raise DomainError("loss_cooldown must be a non-negative timedelta")
        if not isinstance(
            self.max_portfolio_age, timedelta
        ) or self.max_portfolio_age <= timedelta(0):
            raise DomainError("max_portfolio_age must be a positive timedelta")
        if not isinstance(self.emergency_stop, bool):
            raise DomainError("emergency_stop must be boolean")


@dataclass(frozen=True)
class TradeRequest:
    signal_id: uuid.UUID
    token_id: uuid.UUID
    token_mint: str
    levels: PriceLevels
    liquidity_usd: Decimal
    spread_pct: Decimal | None  # None = spread not observed (fail closed, see RiskEngine)
    slippage_pct: Decimal
    token_program: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.signal_id, uuid.UUID) or not isinstance(
            self.token_id, uuid.UUID
        ):
            raise DomainError("signal_id and token_id must be UUID values")
        if not isinstance(self.token_mint, str) or not self.token_mint.strip():
            raise DomainError("token_mint must not be empty")
        if self.token_program is not None and (
            not isinstance(self.token_program, str) or not self.token_program.strip()
        ):
            raise DomainError(
                "token_program must be a non-empty program ID when provided"
            )
        if not isinstance(self.levels, PriceLevels):
            raise DomainError("levels must be validated PriceLevels")
        non_negative(self.liquidity_usd, "liquidity_usd")
        if self.spread_pct is not None:
            percent(self.spread_pct, "spread_pct")
        percent(self.slippage_pct, "slippage_pct")


@dataclass(frozen=True)
class RiskDecision:
    approved: bool
    reasons: tuple[str, ...]
    sizing: SizingResult | None

    def as_audit_payload(self, request: TradeRequest) -> dict:
        return {
            "signal_id": str(request.signal_id),
            "approved": self.approved,
            "reasons": list(self.reasons),
            "size_units": str(self.sizing.size_units) if self.sizing else None,
            "risk_amount_quote": (
                str(self.sizing.risk_amount_quote) if self.sizing else None
            ),
            "exposure_quote": str(self.sizing.exposure_quote) if self.sizing else None,
        }


class RiskEngine:
    def __init__(self, limits: RiskLimits) -> None:
        if not isinstance(limits, RiskLimits):
            raise DomainError("limits must be a validated RiskLimits instance")
        self.limits = limits

    def evaluate(
        self,
        request: TradeRequest,
        portfolio: PortfolioSnapshot,
        now: datetime,
        *,
        token_program_evidence: Token2022ExtensionEvidence | None = None,
    ) -> RiskDecision:
        if not isinstance(request, TradeRequest):
            raise DomainError("request must be a validated TradeRequest")
        if not isinstance(portfolio, PortfolioSnapshot):
            raise DomainError("portfolio must be a validated PortfolioSnapshot")
        now = ensure_utc(now)
        lim = self.limits
        if lim.emergency_stop:
            return RiskDecision(False, ("EMERGENCY_STOP",), None)
        age = now - portfolio.as_of
        if age > lim.max_portfolio_age or age < timedelta(0):
            return RiskDecision(False, ("STALE_PORTFOLIO",), None)
        if portfolio.equity_quote <= 0:
            return RiskDecision(False, ("INVALID_EQUITY",), None)

        reasons: list[str] = []
        if request.token_program is None:
            reasons.append("TOKEN_PROGRAM_EVIDENCE_UNAVAILABLE")
        elif request.token_program not in SUPPORTED_TOKEN_PROGRAMS:
            reasons.append("UNSUPPORTED_TOKEN_PROGRAM")
        if request.token_program == TOKEN_PROGRAM_ID:
            if token_program_evidence is None:
                reasons.append("TOKEN_PROGRAM_EVIDENCE_UNAVAILABLE")
            elif not isinstance(token_program_evidence, Token2022ExtensionEvidence):
                reasons.append("TOKEN_PROGRAM_EVIDENCE_INVALID")
            elif token_program_evidence.mint != request.token_mint:
                reasons.append("TOKEN2022_MINT_MISMATCH")
            elif (
                token_program_evidence.token_program != TOKEN_PROGRAM_ID
                or token_program_evidence.validation_status != REJECTED
                or token_program_evidence.account_data_length != 82
                or "CLASSIC_SPL_MINT_CONFIRMED"
                not in token_program_evidence.reason_codes
            ):
                reasons.append("TOKEN_PROGRAM_EVIDENCE_INVALID")
            else:
                evidence_age = now - ensure_utc(token_program_evidence.observed_at)
                if evidence_age < timedelta(0) or evidence_age > lim.max_portfolio_age:
                    reasons.append("TOKEN_PROGRAM_EVIDENCE_STALE")
        if request.token_program == TOKEN_2022_PROGRAM_ID:
            if (
                token_program_evidence is not None
                and not isinstance(token_program_evidence, Token2022ExtensionEvidence)
            ) or (
                token_program_evidence is not None
                and token_program_evidence.token_program != TOKEN_2022_PROGRAM_ID
            ):
                reasons.append("TOKEN_PROGRAM_EVIDENCE_INVALID")
            else:
                token_gate = evaluate_token_2022_risk(
                    token_program_evidence,
                    expected_mint=request.token_mint,
                    now=now,
                    max_age=lim.max_portfolio_age,
                )
                if not token_gate.approved:
                    reasons.extend(token_gate.reason_codes)
        if portfolio.drawdown_pct >= lim.max_drawdown_pct:
            reasons.append("DRAWDOWN_LIMIT")
        if (
            portfolio.last_loss_at is not None
            and now - portfolio.last_loss_at < lim.loss_cooldown
        ):
            reasons.append("COOLDOWN")
        if portfolio.open_count >= lim.max_open_positions:
            reasons.append("MAX_POSITIONS")
        if request.liquidity_usd < lim.min_liquidity_usd:
            reasons.append("LOW_LIQUIDITY")
        if request.spread_pct is None:
            # Missing evidence is never treated as a tight spread.
            reasons.append("SPREAD_UNAVAILABLE")
        elif request.spread_pct > lim.max_spread_pct:
            reasons.append("SPREAD_TOO_WIDE")
        if request.slippage_pct > lim.max_slippage_pct:
            reasons.append("SLIPPAGE_TOO_HIGH")

        try:
            sizing = size_position(
                equity_quote=portfolio.equity_quote,
                risk_pct=lim.max_risk_per_trade_pct,
                levels=request.levels,
                fee_rate=lim.fee_rate,
                slippage_rate=request.slippage_pct / Decimal(100),
            )
        except DomainError:
            return RiskDecision(False, tuple(reasons + ["ZERO_STOP_DISTANCE"]), None)

        budget = portfolio.equity_quote * lim.max_risk_per_trade_pct / Decimal(100)
        if sizing.risk_amount_quote + sizing.estimated_fees_quote > budget + Decimal(
            "1E-18"
        ):
            reasons.append("RISK_LIMIT")
        if (
            portfolio.open_exposure_quote + sizing.exposure_quote
            > lim.max_exposure_quote
        ):
            reasons.append("EXPOSURE_LIMIT")
        if reasons:
            return RiskDecision(False, tuple(dict.fromkeys(reasons)), sizing)
        return RiskDecision(True, (), sizing)


class ExposureReservations:
    """Atomic check-and-reserve for notional exposure. Prevents overshoot under concurrency."""

    def __init__(self, limit_quote: Decimal) -> None:
        self._limit = positive(limit_quote, "limit_quote")
        self._reserved = ZERO
        self._lock = threading.Lock()

    @property
    def reserved(self) -> Decimal:
        with self._lock:
            return self._reserved

    def try_reserve(self, amount: Decimal, current_open_exposure: Decimal) -> bool:
        amount = positive(amount, "reservation amount")
        current_open_exposure = non_negative(
            current_open_exposure, "current_open_exposure"
        )
        with self._lock:
            if current_open_exposure + self._reserved + amount > self._limit:
                return False
            self._reserved += amount
            return True

    def release(self, amount: Decimal) -> None:
        amount = positive(amount, "release amount")
        with self._lock:
            self._reserved = max(ZERO, self._reserved - amount)
