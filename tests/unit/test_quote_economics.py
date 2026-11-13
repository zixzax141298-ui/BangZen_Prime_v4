import unittest
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from bangzen_prime.domain.quote_economics import (
    ENTRY,
    EXIT,
    RawPlatformFee,
    RawSwapQuote,
    VerifiedMintDecimals,
    VerifiedQuotePrice,
    normalize_jupiter_quote,
)
from bangzen_prime.errors import DomainError
from tests.support import SOL_MINT, TOKEN_MINT

D = Decimal
NOW = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)


def mint(mint_address, decimals, *, observed=NOW, status="VERIFIED"):
    return VerifiedMintDecimals(
        mint=mint_address, decimals=decimals, source="solana_rpc:getAccountInfo",
        observed_at=observed, validation_status=status, slot=400,
    )


def price(mint_address, quote_mint, value, *, observed=NOW, status="VERIFIED"):
    return VerifiedQuotePrice(
        mint=mint_address, quote_mint=quote_mint, quote_per_token=D(value),
        source="validated_market_price", observed_at=observed,
        validation_status=status, slot=400,
    )


def quote(*, fee=True):
    return RawSwapQuote(
        input_mint=SOL_MINT, output_mint=TOKEN_MINT,
        input_amount_raw=D("1000000000"), output_amount_raw=D("25000000"),
        platform_fee=(
            RawPlatformFee(D("1000000"), SOL_MINT) if fee else None
        ),
    )


class NormalizeJupiterQuoteTests(unittest.TestCase):
    def normalize(self, **changes):
        args = {
            "quote": quote(),
            "quote_observed_at": NOW,
            "quote_currency_mint": SOL_MINT,
            "input_mint_metadata": mint(SOL_MINT, 9),
            "output_mint_metadata": mint(TOKEN_MINT, 6),
            "fee_mint_metadata": mint(SOL_MINT, 9),
            "input_price": None,
            "fee_price": None,
            "now": NOW,
            "max_age": timedelta(seconds=30),
        }
        args.update(changes)
        return normalize_jupiter_quote(**args)

    def test_normalizes_raw_units_and_identity_quote_currency(self):
        result = self.normalize()
        self.assertEqual(result.input_amount, D("1"))
        self.assertEqual(result.output_amount, D("25"))
        self.assertEqual(result.input_notional_quote, D("1"))
        self.assertEqual(result.platform_fee_amount, D("0.001"))
        self.assertEqual(result.platform_fee_quote, D("0.001"))
        self.assertEqual(result.input_price_source, "IDENTITY")

    def test_converts_non_quote_fee_using_verified_fresh_price(self):
        other_fee_mint = TOKEN_MINT
        changed_quote = RawSwapQuote(
            input_mint=SOL_MINT, output_mint=TOKEN_MINT,
            input_amount_raw=D("1000000000"), output_amount_raw=D("25000000"),
            platform_fee=RawPlatformFee(D("250000"), other_fee_mint),
        )
        result = self.normalize(
            quote=changed_quote,
            fee_mint_metadata=mint(other_fee_mint, 6),
            fee_price=price(other_fee_mint, SOL_MINT, "0.02"),
        )
        self.assertEqual(result.platform_fee_amount, D("0.25"))
        self.assertEqual(result.platform_fee_quote, D("0.005"))
        self.assertEqual(result.fee_price_source, "validated_market_price")

    def test_converts_non_quote_input_to_quote_notional(self):
        result = self.normalize(
            quote_currency_mint=TOKEN_MINT,
            input_price=price(SOL_MINT, TOKEN_MINT, "25"),
            fee_price=price(SOL_MINT, TOKEN_MINT, "25"),
        )
        self.assertEqual(result.input_notional_quote, D("25"))
        self.assertEqual(result.platform_fee_quote, D("0.025"))

    def test_maps_platform_fee_to_explicit_entry_or_exit_cost(self):
        result = self.normalize()
        self.assertEqual(
            result.to_execution_costs(fee_side=ENTRY).entry_fee_quote, D("0.001")
        )
        self.assertEqual(
            result.to_execution_costs(fee_side=EXIT).exit_fee_quote, D("0.001")
        )
        with self.assertRaises(DomainError):
            result.to_execution_costs(fee_side="UNKNOWN")

    def test_missing_platform_fee_is_not_silently_zero(self):
        result = self.normalize(quote=quote(fee=False), fee_mint_metadata=None)
        self.assertIsNone(result.platform_fee_quote)
        with self.assertRaises(DomainError):
            result.to_execution_costs(fee_side=ENTRY)

    def test_rejects_missing_or_mismatched_mint_metadata(self):
        with self.assertRaises(DomainError):
            self.normalize(input_mint_metadata=None)
        with self.assertRaises(DomainError):
            self.normalize(output_mint_metadata=mint(SOL_MINT, 6))

    def test_rejects_stale_and_future_mint_or_quote_evidence(self):
        with self.assertRaises(DomainError):
            self.normalize(input_mint_metadata=mint(
                SOL_MINT, 9, observed=NOW - timedelta(seconds=31)
            ))
        with self.assertRaises(DomainError):
            self.normalize(quote_observed_at=NOW + timedelta(seconds=1))

    def test_rejects_unverified_mint_or_price_evidence(self):
        with self.assertRaises(DomainError):
            self.normalize(input_mint_metadata=mint(SOL_MINT, 9, status="PARTIAL"))
        with self.assertRaises(DomainError):
            self.normalize(
                quote_currency_mint=TOKEN_MINT,
                input_price=price(SOL_MINT, TOKEN_MINT, "25", status="PARTIAL"),
            )

    def test_rejects_missing_stale_or_mismatched_fee_price(self):
        changed_quote = RawSwapQuote(
            input_mint=SOL_MINT, output_mint=TOKEN_MINT,
            input_amount_raw=D("1000000000"), output_amount_raw=D("25000000"),
            platform_fee=RawPlatformFee(D("100000"), TOKEN_MINT),
        )
        with self.assertRaises(DomainError):
            self.normalize(
                quote=changed_quote,
                fee_mint_metadata=mint(TOKEN_MINT, 6),
            )
        with self.assertRaises(DomainError):
            self.normalize(
                quote=changed_quote,
                fee_mint_metadata=mint(TOKEN_MINT, 6),
                fee_price=price(TOKEN_MINT, SOL_MINT, "0.02",
                                observed=NOW - timedelta(seconds=31)),
            )

    def test_rejects_invalid_decimals_and_price(self):
        with self.assertRaises(DomainError):
            mint(SOL_MINT, True)
        with self.assertRaises(DomainError):
            price(SOL_MINT, TOKEN_MINT, "0")


if __name__ == "__main__":
    unittest.main()
