"""Signal domain models and validated price geometry.

Signals are research outputs, not execution authorizations or profit guarantees.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum

from bangzen_prime.domain.shared import AggregateRoot, ensure_utc
from bangzen_prime.domain.tokens import (
    pair_identity,
    token_identity,
    validate_chain,
    validate_mint,
)
from bangzen_prime.domain.values import positive, unit_interval
from bangzen_prime.errors import DomainError


class RejectReason(str, Enum):
    RISK_TOO_HIGH = "RISK_TOO_HIGH"
    MARKET_UNAVAILABLE = "MARKET_UNAVAILABLE"
    EMPTY_MARKET = "EMPTY_MARKET"
    STALE_MARKET = "STALE_MARKET"
    SAFETY_UNAVAILABLE = "SAFETY_UNAVAILABLE"
    SAFETY_BLOCKED = "SAFETY_BLOCKED"
    RUGGED = "RUGGED"
    TOKEN_PROGRAM_EVIDENCE_UNAVAILABLE = "TOKEN_PROGRAM_EVIDENCE_UNAVAILABLE"
    TOKEN_PROGRAM_UNSUPPORTED = "TOKEN_PROGRAM_UNSUPPORTED"
    TOKEN2022_EVIDENCE_STALE = "TOKEN2022_EVIDENCE_STALE"
    TOKEN2022_EVIDENCE_NOT_VERIFIED = "TOKEN2022_EVIDENCE_NOT_VERIFIED"
    TOKEN2022_EVIDENCE_REJECTED = "TOKEN2022_EVIDENCE_REJECTED"
    TOKEN2022_MINT_MISMATCH = "TOKEN2022_MINT_MISMATCH"
    TOKEN2022_HARD_VETO = "TOKEN2022_HARD_VETO"
    TOKEN2022_REVIEW_REQUIRED = "TOKEN2022_REVIEW_REQUIRED"
    HOLDER_DATA_UNAVAILABLE = "HOLDER_DATA_UNAVAILABLE"
    SYBIL_UNAVAILABLE = "SYBIL_UNAVAILABLE"
    SYBIL_CLUSTER_DETECTED = "SYBIL_CLUSTER_DETECTED"
    INTEL_UNAVAILABLE = "INTEL_UNAVAILABLE"
    AI_UNAVAILABLE = "AI_UNAVAILABLE"
    AI_OUTPUT_INVALID = "AI_OUTPUT_INVALID"
    AI_REJECTED = "AI_REJECTED"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
    NO_VOLATILITY = "NO_VOLATILITY"
    LOW_LIQUIDITY = "LOW_LIQUIDITY"
    LOW_SCORE = "LOW_SCORE"
    INVALID_LEVELS = "INVALID_LEVELS"
    LOW_RISK_REWARD = "LOW_RISK_REWARD"
    PHASE_WATCH_ONLY = "PHASE_WATCH_ONLY"
    PHASE_EVIDENCE_MISSING = "PHASE_EVIDENCE_MISSING"
    RISK_GOVERNOR_PAUSED = "RISK_GOVERNOR_PAUSED"
    DUPLICATE_CANDIDATE = "DUPLICATE_CANDIDATE"


class SignalStatus(str, Enum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    WATCH = "WATCH"


class AIMode(str, Enum):
    DISABLED = "DISABLED"
    ADVISORY = "ADVISORY"
    REQUIRED = "REQUIRED"


@dataclass(frozen=True)
class PriceLevels:
    """Long-only geometry: 0 < stop_loss < entry < take_profit."""

    entry: Decimal
    stop_loss: Decimal
    take_profit: Decimal

    def __post_init__(self) -> None:
        entry = positive(self.entry, "entry")
        stop = positive(self.stop_loss, "stop_loss")
        target = positive(self.take_profit, "take_profit")
        if not stop < entry < target:
            raise DomainError("long levels must satisfy stop_loss < entry < take_profit")
        object.__setattr__(self, "entry", entry)
        object.__setattr__(self, "stop_loss", stop)
        object.__setattr__(self, "take_profit", target)

    @property
    def risk_per_unit(self) -> Decimal:
        return self.entry - self.stop_loss

    @property
    def reward_per_unit(self) -> Decimal:
        return self.take_profit - self.entry

    @property
    def risk_reward(self) -> Decimal:
        return self.reward_per_unit / self.risk_per_unit


class Signal(AggregateRoot):
    """Validated signal aggregate with a stable identity and explicit lifecycle state."""

    def __init__(
        self,
        *,
        token_id: uuid.UUID,
        pair_id: uuid.UUID,
        status: SignalStatus,
        score: Decimal,
        reasons: tuple[RejectReason, ...],
        created_at: datetime,
        levels: PriceLevels | None = None,
        confidence: Decimal | None = None,
        signal_id: uuid.UUID | None = None,
    ) -> None:
        super().__init__(signal_id or uuid.uuid4())
        if not isinstance(token_id, uuid.UUID) or not isinstance(pair_id, uuid.UUID):
            raise DomainError("signal token_id and pair_id must be UUID values")
        if not isinstance(status, SignalStatus):
            raise DomainError("signal status is invalid")
        if status is SignalStatus.ACCEPTED:
            if not isinstance(levels, PriceLevels) or confidence is None or reasons:
                raise DomainError("accepted signal needs levels and confidence and no reasons")
            unit_interval(confidence, "confidence")
        elif status in (SignalStatus.REJECTED, SignalStatus.WATCH):
            if not reasons or levels is not None or confidence is not None:
                raise DomainError("rejected/watch signal needs reasons and no levels or confidence")
        else:
            raise DomainError("unknown signal status")
        self.token_id = token_id
        self.pair_id = pair_id
        self.status = status
        self.score = score
        self.reasons = tuple(reasons)
        self.created_at = ensure_utc(created_at)
        self.levels = levels
        self.confidence = confidence

    @classmethod
    def accept(
        cls, *, token_id: uuid.UUID, pair_id: uuid.UUID, score: Decimal,
        confidence: Decimal, levels: PriceLevels, created_at: datetime,
        chain: str | None = None, mint: str | None = None,
        symbol: str | None = None, pair_address: str | None = None,
        dex_id: str | None = None, market_source: str | None = None,
        market_observed_at: datetime | None = None,
    ) -> Signal:
        signal = cls(
            token_id=token_id, pair_id=pair_id, status=SignalStatus.ACCEPTED,
            score=score, reasons=(), created_at=created_at, levels=levels,
            confidence=confidence,
        )
        metadata = (chain, mint, symbol, pair_address, dex_id, market_source, market_observed_at)
        if any(value is not None for value in metadata):
            if any(value is None for value in metadata):
                raise DomainError("signal market identity and provenance must be supplied together")
            if (
                not isinstance(chain, str)
                or not isinstance(mint, str)
                or not isinstance(symbol, str)
                or not isinstance(pair_address, str)
                or not isinstance(dex_id, str)
                or not isinstance(market_source, str)
                or not isinstance(market_observed_at, datetime)
            ):
                raise DomainError("signal market identity and provenance have invalid types")
            validate_chain(chain)
            validate_mint(mint)
            if token_identity(chain, mint) != token_id:
                raise DomainError("signal mint does not match token identity")
            if pair_identity(chain, pair_address) != pair_id:
                raise DomainError("signal pair address does not match pair identity")
            if not isinstance(symbol, str) or not symbol or len(symbol) > 32 or not symbol.isprintable():
                raise DomainError("signal symbol must be 1-32 printable characters")
            if not isinstance(dex_id, str) or not dex_id.strip() or len(dex_id) > 64:
                raise DomainError("signal DEX id is invalid")
            if not isinstance(market_source, str) or not market_source.strip() or len(market_source) > 64:
                raise DomainError("signal market source is invalid")
            observed_at = ensure_utc(market_observed_at)
        else:
            observed_at = None

        payload = {
            "signal_id": str(signal.id),
            "token_id": str(token_id),
            "entry": str(levels.entry),
            "stop_loss": str(levels.stop_loss),
            "take_profit": str(levels.take_profit),
            "confidence": str(confidence),
            "score": str(score),
            "label": "SIGNAL_ONLY",
        }
        if observed_at is not None:
            payload.update({
                "chain": chain,
                "mint": mint,
                "symbol": symbol,
                "pair_address": pair_address,
                "dex_id": dex_id,
                "market_source": market_source,
                "market_observed_at": observed_at.isoformat(),
            })
        signal.record_event("SignalGenerated", payload, created_at)
        return signal

    @classmethod
    def reject(
        cls, *, token_id: uuid.UUID, pair_id: uuid.UUID, score: Decimal,
        reasons: tuple[RejectReason, ...], created_at: datetime,
    ) -> Signal:
        return cls(
            token_id=token_id, pair_id=pair_id, status=SignalStatus.REJECTED,
            score=score, reasons=reasons, created_at=created_at,
        )


@dataclass(frozen=True)
class ResiliencePolicy:
    """Domain-level breaker policy; infrastructure decides how to enforce it."""

    failure_threshold: int = 5
    recovery_seconds: float = 30.0

    def __post_init__(self) -> None:
        if isinstance(self.failure_threshold, bool) or self.failure_threshold < 1:
            raise DomainError("failure_threshold must be a positive integer")
        if not isinstance(self.failure_threshold, int):
            raise DomainError("failure_threshold must be a positive integer")
        if (isinstance(self.recovery_seconds, bool)
                or not isinstance(self.recovery_seconds, (int, float))
                or not math.isfinite(self.recovery_seconds)
                or self.recovery_seconds <= 0):
            raise DomainError("recovery_seconds must be a finite positive number")


@dataclass(frozen=True)
class ResilienceConfig:
    market_breaker: ResiliencePolicy
    safety_breaker: ResiliencePolicy
    holder_breaker: ResiliencePolicy
    intel_breaker: ResiliencePolicy
    ai_breaker: ResiliencePolicy

    def __post_init__(self) -> None:
        if any(not isinstance(policy, ResiliencePolicy) for policy in (
            self.market_breaker, self.safety_breaker, self.holder_breaker,
            self.intel_breaker, self.ai_breaker,
        )):
            raise DomainError("all resilience policies must be validated ResiliencePolicy values")
