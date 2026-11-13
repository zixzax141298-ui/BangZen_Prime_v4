"""Ports (interfaces) implemented by infrastructure adapters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from bangzen_prime.domain.execution import PlannedTransaction, Quote
from bangzen_prime.domain.tokens import PairSnapshot, SafetyAssessment


class MarketDataPort(Protocol):
    def fetch_pairs(self, chain: str, mint: str) -> list[PairSnapshot]:
        """Return validated pair snapshots for a base token. Raise ExternalServiceError on failure."""
        ...


class TokenSafetyPort(Protocol):
    def fetch_safety(self, chain: str, mint: str) -> SafetyAssessment:
        """Return a normalised safety assessment. Raise ExternalServiceError on failure."""
        ...


@dataclass(frozen=True)
class MarketSentimentObservation:
    """Verified ecosystem-level sentiment observation; never token-specific by ticker."""

    topic: str
    sentiment_pct: Decimal
    interactions_24h: int
    contributors_24h: int
    posts_24h: int
    trend: str
    generated_at: datetime
    source: str


class MarketSentimentPort(Protocol):
    def fetch_market_sentiment(self) -> MarketSentimentObservation:
        """Return cached macro sentiment for the configured market topic."""
        ...


class HolderProfilePort(Protocol):
    mint: str
    holder_count: int
    top_holder_share_pct: Decimal | None
    source: str


class HolderDataPort(Protocol):
    def holder_profile(self, chain: str, mint: str) -> HolderProfilePort:
        """Return a validated holder count and concentration observation."""
        ...


class Notifier(Protocol):
    def send(self, text: str) -> None:
        """Deliver one message. Raise on failure so the caller can retry."""
        ...


class QuotePort(Protocol):
    def quote(self, input_mint: str, output_mint: str, in_amount: Decimal) -> Quote:
        """Return a route quote. Raise ExternalServiceError on failure."""
        ...


class TransactionBuilderPort(Protocol):
    def build(self, quote: Quote) -> PlannedTransaction:
        """Turn a quote into a transaction plan. Must not sign."""
        ...


@dataclass(frozen=True)
class SimulationResult:
    ok: bool
    error_code: str | None = None


class RpcPort(Protocol):
    def simulate(self, plan: PlannedTransaction) -> SimulationResult: ...

    def send(self, signed: SignedTransaction) -> str:
        """Broadcast and return a signature. Only reachable through an approved signer."""
        ...

    def signature_status(self, signature: str) -> str:
        """One of NOT_FOUND, PROCESSED, CONFIRMED, FINALIZED, FAILED."""
        ...

    def token_balance(self, owner: str, mint: str) -> Decimal: ...


@dataclass(frozen=True)
class SignedTransaction:
    raw: bytes
    plan: PlannedTransaction


class TransactionSigner(Protocol):
    def sign(self, plan: PlannedTransaction) -> SignedTransaction: ...
