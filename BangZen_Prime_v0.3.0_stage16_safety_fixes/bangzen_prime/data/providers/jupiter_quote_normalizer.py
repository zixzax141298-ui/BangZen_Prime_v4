"""Map the validated Jupiter provider DTO into provider-neutral domain economics."""

from __future__ import annotations

from datetime import datetime, timedelta

from bangzen_prime.core.errors import DomainError
from bangzen_prime.data.providers.jupiter_quote_v2 import JupiterQuoteV2
from bangzen_prime.execution.quote_economics import (
    NormalizedJupiterQuote,
    RawPlatformFee,
    RawSwapQuote,
    VerifiedMintDecimals,
    VerifiedQuotePrice,
    normalize_jupiter_quote,
)


def normalize_provider_quote(
    *,
    quote: JupiterQuoteV2,
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
    """Translate Jupiter's DTO into the pure domain contract and normalize it."""
    if not isinstance(quote, JupiterQuoteV2):
        raise DomainError("quote must be a validated JupiterQuoteV2")
    platform_fee = None
    if quote.platform_fee is not None:
        platform_fee = RawPlatformFee(
            amount_raw=quote.platform_fee.amount_raw,
            fee_mint=quote.platform_fee.fee_mint,
        )
    domain_quote = RawSwapQuote(
        input_mint=quote.input_mint,
        output_mint=quote.output_mint,
        input_amount_raw=quote.input_amount_raw,
        output_amount_raw=quote.output_amount_raw,
        platform_fee=platform_fee,
    )
    return normalize_jupiter_quote(
        quote=domain_quote,
        quote_observed_at=quote_observed_at,
        quote_currency_mint=quote_currency_mint,
        input_mint_metadata=input_mint_metadata,
        output_mint_metadata=output_mint_metadata,
        fee_mint_metadata=fee_mint_metadata,
        input_price=input_price,
        fee_price=fee_price,
        now=now,
        max_age=max_age,
    )
