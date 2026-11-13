"""Chain execution value objects: quotes, planned transactions, inspection rules.

Nothing here signs or sends anything. These types describe and check a plan.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from bangzen_prime.domain.shared import ensure_utc
from bangzen_prime.domain.tokens import validate_mint
from bangzen_prime.domain.values import percent, positive
from bangzen_prime.errors import DomainError


@dataclass(frozen=True)
class Quote:
    provider: str
    input_mint: str
    output_mint: str
    in_amount: Decimal
    out_amount: Decimal
    price_impact_pct: Decimal
    quoted_at: datetime
    expires_at: datetime

    @classmethod
    def create(cls, *, provider: str, input_mint: str, output_mint: str, in_amount: object,
               out_amount: object, price_impact_pct: object, quoted_at: datetime,
               expires_at: datetime) -> Quote:
        validate_mint(input_mint)
        validate_mint(output_mint)
        if input_mint == output_mint:
            raise DomainError("input and output mint must differ")
        if not provider.strip():
            raise DomainError("quote provider is required")
        quoted = ensure_utc(quoted_at)
        expires = ensure_utc(expires_at)
        if expires <= quoted:
            raise DomainError("quote expiry must be after quote time")
        return cls(provider.strip(), input_mint, output_mint, positive(in_amount, "in_amount"),
                   positive(out_amount, "out_amount"), percent(price_impact_pct, "price_impact_pct"),
                   quoted, expires)

    def is_expired(self, now: datetime) -> bool:
        return ensure_utc(now) >= self.expires_at


@dataclass(frozen=True)
class Transfer:
    mint: str
    amount: Decimal
    source_owner: str
    destination: str

    def __post_init__(self) -> None:
        validate_mint(self.mint)
        positive(self.amount, "transfer amount")


@dataclass(frozen=True)
class PlannedTransaction:
    provider: str
    program_ids: tuple[str, ...]
    transfers: tuple[Transfer, ...]
    fee_payer: str
    expires_at: datetime


ALLOWED_PROVIDERS = frozenset({"jupiter-compatible"})


def validate_quote(quote: Quote, *, now: datetime, expected_input: str, expected_output: str,
                   expected_in_amount: Decimal, max_price_impact_pct: Decimal,
                   allowed_providers: frozenset[str] = ALLOWED_PROVIDERS) -> list[str]:
    """Return reason codes. Empty list means the quote is usable."""
    reasons: list[str] = []
    if quote.provider not in allowed_providers:
        reasons.append("ROUTE_PROVIDER_NOT_ALLOWED")
    if quote.input_mint != expected_input or quote.output_mint != expected_output:
        reasons.append("WRONG_MINT")
    if quote.in_amount != expected_in_amount:
        reasons.append("AMOUNT_MISMATCH")
    if quote.is_expired(now):
        reasons.append("QUOTE_STALE")
    if quote.price_impact_pct > max_price_impact_pct:
        reasons.append("PRICE_IMPACT_TOO_HIGH")
    return reasons


def inspect_plan(plan: PlannedTransaction, *, quote: Quote, owner: str,
                 allowed_programs: frozenset[str], allowed_destinations: frozenset[str],
                 now: datetime) -> list[str]:
    """Static checks on a planned transaction before any simulation. Empty list means pass."""
    reasons: list[str] = []
    if plan.provider != quote.provider:
        reasons.append("PLAN_PROVIDER_MISMATCH")
    if ensure_utc(now) >= ensure_utc(plan.expires_at):
        reasons.append("PLAN_EXPIRED")
    if any(p not in allowed_programs for p in plan.program_ids):
        reasons.append("UNKNOWN_PROGRAM")
    if plan.fee_payer != owner:
        reasons.append("FEE_PAYER_NOT_OWNER")
    if any(t.source_owner != owner for t in plan.transfers):
        reasons.append("FOREIGN_SOURCE")
    if any(t.destination not in allowed_destinations for t in plan.transfers):
        reasons.append("UNKNOWN_DESTINATION")
    spent = sum((t.amount for t in plan.transfers if t.mint == quote.input_mint), Decimal(0))
    if spent != quote.in_amount:
        reasons.append("TRANSFER_TOTAL_MISMATCH")
    return reasons


def balance_delta_matches(*, before: Decimal, after: Decimal, expected_increase: Decimal,
                          tolerance_pct: Decimal) -> bool:
    """Check that an observed balance change matches the quoted output within a tolerance."""
    if expected_increase <= 0:
        raise DomainError("expected increase must be positive")
    observed = after - before
    allowed = expected_increase * tolerance_pct / Decimal(100)
    return abs(observed - expected_increase) <= allowed
