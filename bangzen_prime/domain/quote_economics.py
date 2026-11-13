"""Normalize Jupiter raw token amounts and value explicit fees in quote currency.

This module is pure domain logic. It consumes already validated mint/price evidence;
it does not fetch RPC data, infer missing fees, or authorize execution.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation, localcontext

from bangzen_prime.domain.execution_economics import ExecutionCostBreakdown
from bangzen_prime.domain.tokens import validate_mint
from bangzen_prime.errors import DomainError

ZERO = Decimal("0")
VERIFIED = "VERIFIED"
ENTRY = "ENTRY"
EXIT = "EXIT"


def _aware_utc(value: datetime, name: str) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise DomainError(f"{name} must be timezone-aware")
    return value


def _freshness(
    *, observed_at: datetime, now: datetime, max_age: timedelta, name: str
) -> None:
    observed = _aware_utc(observed_at, f"{name}.observed_at")
    current = _aware_utc(now, "now")
    if not isinstance(max_age, timedelta) or max_age <= timedelta(0):
        raise DomainError("max_age must be a positive timedelta")
    age = current - observed
    if age < timedelta(0) or age > max_age:
        raise DomainError(f"{name} is stale or from the future")


def _source(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DomainError(f"{name} source is required")
    return value.strip()


@dataclass(frozen=True)
class RawPlatformFee:
    amount_raw: Decimal
    fee_mint: str

    def __post_init__(self) -> None:
        if not isinstance(self.amount_raw, Decimal) or not self.amount_raw.is_finite():
            raise DomainError("platform fee raw amount must be a finite Decimal")
        if self.amount_raw < ZERO:
            raise DomainError("platform fee raw amount must not be negative")
        validate_mint(self.fee_mint)


@dataclass(frozen=True)
class RawSwapQuote:
    """Provider-neutral quote fields needed by deterministic domain accounting."""

    input_mint: str
    output_mint: str
    input_amount_raw: Decimal
    output_amount_raw: Decimal
    platform_fee: RawPlatformFee | None = None

    def __post_init__(self) -> None:
        validate_mint(self.input_mint)
        validate_mint(self.output_mint)
        if self.input_mint == self.output_mint:
            raise DomainError("swap quote mints must differ")
        for name, amount in (
            ("input_amount_raw", self.input_amount_raw),
            ("output_amount_raw", self.output_amount_raw),
        ):
            if (
                not isinstance(amount, Decimal)
                or not amount.is_finite()
                or amount <= ZERO
            ):
                raise DomainError(f"{name} must be a finite positive Decimal")
        if self.platform_fee is not None and not isinstance(
            self.platform_fee, RawPlatformFee
        ):
            raise DomainError("platform_fee must be a validated RawPlatformFee")


@dataclass(frozen=True)
class VerifiedMintDecimals:
    """Mint decimals with upstream provenance and explicit validation state."""

    mint: str
    decimals: int
    source: str
    observed_at: datetime
    validation_status: str
    slot: int | None = None

    def __post_init__(self) -> None:
        validate_mint(self.mint)
        if (
            isinstance(self.decimals, bool)
            or not isinstance(self.decimals, int)
            or not 0 <= self.decimals <= 255
        ):
            raise DomainError("mint decimals must be an integer within [0, 255]")
        _source(self.source, "mint metadata")
        _aware_utc(self.observed_at, "mint metadata observed_at")
        if self.validation_status != VERIFIED:
            raise DomainError("mint metadata must have VERIFIED validation status")
        if self.slot is not None and (
            isinstance(self.slot, bool)
            or not isinstance(self.slot, int)
            or self.slot < 0
        ):
            raise DomainError("mint metadata slot must be a non-negative integer")


@dataclass(frozen=True)
class VerifiedQuotePrice:
    """Price of one whole token in quote-currency units."""

    mint: str
    quote_mint: str
    quote_per_token: Decimal
    source: str
    observed_at: datetime
    validation_status: str
    slot: int | None = None

    def __post_init__(self) -> None:
        validate_mint(self.mint)
        validate_mint(self.quote_mint)
        if self.mint == self.quote_mint:
            raise DomainError("same-mint conversion must use the identity rate")
        if isinstance(self.quote_per_token, bool) or not isinstance(
            self.quote_per_token, (str, int, Decimal)
        ):
            raise DomainError("quote_per_token must be a Decimal-compatible value")
        try:
            price = Decimal(str(self.quote_per_token))
        except (InvalidOperation, ValueError):
            raise DomainError("quote_per_token is invalid") from None
        if not price.is_finite() or price <= ZERO:
            raise DomainError("quote_per_token must be finite and positive")
        object.__setattr__(self, "quote_per_token", price)
        _source(self.source, "price evidence")
        _aware_utc(self.observed_at, "price evidence observed_at")
        if self.validation_status != VERIFIED:
            raise DomainError("price evidence must have VERIFIED validation status")
        if self.slot is not None and (
            isinstance(self.slot, bool)
            or not isinstance(self.slot, int)
            or self.slot < 0
        ):
            raise DomainError("price evidence slot must be a non-negative integer")


@dataclass(frozen=True)
class NormalizedJupiterQuote:
    input_amount: Decimal
    output_amount: Decimal
    input_notional_quote: Decimal
    platform_fee_amount: Decimal | None
    platform_fee_quote: Decimal | None
    quote_currency_mint: str
    input_decimals_source: str
    output_decimals_source: str
    fee_decimals_source: str | None
    input_price_source: str
    fee_price_source: str | None
    observed_at: datetime

    def to_execution_costs(self, *, fee_side: str) -> ExecutionCostBreakdown:
        """Map explicit platform fees to a lifecycle side; never infer missing fees."""
        if fee_side not in (ENTRY, EXIT):
            raise DomainError("fee_side must be ENTRY or EXIT")
        if self.platform_fee_quote is None:
            raise DomainError(
                "platform fee amount is unavailable; cannot build fee costs"
            )
        if fee_side == ENTRY:
            return ExecutionCostBreakdown(entry_fee_quote=self.platform_fee_quote)
        return ExecutionCostBreakdown(exit_fee_quote=self.platform_fee_quote)


def _token_units(raw_amount: Decimal, decimals: int, name: str) -> Decimal:
    if (
        not isinstance(raw_amount, Decimal)
        or not raw_amount.is_finite()
        or raw_amount < ZERO
    ):
        raise DomainError(f"{name} must be a finite non-negative Decimal")
    with localcontext() as context:
        context.prec = 300
        return raw_amount.scaleb(-decimals)


def _require_mint_evidence(
    evidence: VerifiedMintDecimals,
    *,
    mint: str,
    now: datetime,
    max_age: timedelta,
    name: str,
) -> None:
    if not isinstance(evidence, VerifiedMintDecimals) or evidence.mint != mint:
        raise DomainError(f"{name} mint metadata is missing or mismatched")
    _freshness(observed_at=evidence.observed_at, now=now, max_age=max_age, name=name)


def _quote_rate(
    *,
    mint: str,
    quote_mint: str,
    evidence: VerifiedQuotePrice | None,
    now: datetime,
    max_age: timedelta,
    name: str,
) -> tuple[Decimal, str]:
    if mint == quote_mint:
        return Decimal("1"), "IDENTITY"
    if not isinstance(evidence, VerifiedQuotePrice):
        raise DomainError(f"{name} conversion evidence is unavailable")
    if evidence.mint != mint or evidence.quote_mint != quote_mint:
        raise DomainError(f"{name} conversion evidence has mismatched mints")
    _freshness(observed_at=evidence.observed_at, now=now, max_age=max_age, name=name)
    return evidence.quote_per_token, evidence.source


def normalize_jupiter_quote(
    *,
    quote: object,
    quote_observed_at: datetime,
    quote_currency_mint: str,
    input_mint_metadata: VerifiedMintDecimals,
    output_mint_metadata: VerifiedMintDecimals,
    fee_mint_metadata: VerifiedMintDecimals | None,
    input_price: VerifiedQuotePrice | None,
    fee_price: VerifiedQuotePrice | None,
    now: datetime,
    max_age: timedelta,
) -> NormalizedJupiterQuote:
    """Normalize one validated Jupiter quote; missing critical evidence fails closed.

    Platform fee is converted only when its exact raw amount is present. The total
    feeBps field is deliberately not converted into a guessed amount.
    """
    if not isinstance(quote, RawSwapQuote):
        raise DomainError("quote must be a validated RawSwapQuote")
    validate_mint(quote_currency_mint)
    _freshness(
        observed_at=quote_observed_at, now=now, max_age=max_age, name="Jupiter quote"
    )
    _require_mint_evidence(
        input_mint_metadata, mint=quote.input_mint, now=now, max_age=max_age,
        name="input",
    )
    _require_mint_evidence(
        output_mint_metadata, mint=quote.output_mint, now=now, max_age=max_age,
        name="output",
    )
    input_amount = _token_units(
        quote.input_amount_raw, input_mint_metadata.decimals, "input amount"
    )
    output_amount = _token_units(
        quote.output_amount_raw, output_mint_metadata.decimals, "output amount"
    )
    input_rate, input_price_source = _quote_rate(
        mint=quote.input_mint, quote_mint=quote_currency_mint, evidence=input_price,
        now=now, max_age=max_age, name="input price",
    )
    with localcontext() as context:
        context.prec = 100
        input_notional_quote = input_amount * input_rate

    fee_amount = None
    fee_quote = None
    fee_source = None
    fee_decimals_source = None
    if quote.platform_fee is not None:
        fee_mint = quote.platform_fee.fee_mint
        _require_mint_evidence(
            fee_mint_metadata, mint=fee_mint, now=now, max_age=max_age,
            name="fee",
        )
        fee_amount = _token_units(
            quote.platform_fee.amount_raw, fee_mint_metadata.decimals, "platform fee"
        )
        fee_rate, fee_source = _quote_rate(
            mint=fee_mint, quote_mint=quote_currency_mint, evidence=fee_price,
            now=now, max_age=max_age, name="fee price",
        )
        with localcontext() as context:
            context.prec = 100
            fee_quote = fee_amount * fee_rate
        fee_decimals_source = fee_mint_metadata.source

    return NormalizedJupiterQuote(
        input_amount=input_amount,
        output_amount=output_amount,
        input_notional_quote=input_notional_quote,
        platform_fee_amount=fee_amount,
        platform_fee_quote=fee_quote,
        quote_currency_mint=quote_currency_mint,
        input_decimals_source=input_mint_metadata.source,
        output_decimals_source=output_mint_metadata.source,
        fee_decimals_source=fee_decimals_source,
        input_price_source=input_price_source,
        fee_price_source=fee_source,
        observed_at=quote_observed_at,
    )
