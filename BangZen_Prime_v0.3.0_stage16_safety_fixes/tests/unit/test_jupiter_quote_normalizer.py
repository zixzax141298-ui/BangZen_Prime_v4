import unittest
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from bangzen_prime.data.providers.jupiter_quote_normalizer import (
    normalize_provider_quote,
)
from bangzen_prime.data.providers.jupiter_quote_v2 import (
    JupiterPlatformFee,
    JupiterQuoteV2,
)
from bangzen_prime.execution.quote_economics import VerifiedMintDecimals
from tests.support import SOL_MINT, TOKEN_MINT

NOW = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)


class JupiterQuoteEconomicsApplicationTests(unittest.TestCase):
    def test_maps_adapter_quote_to_domain_and_normalizes(self):
        quote = JupiterQuoteV2(
            request_id="req-1",
            input_mint=SOL_MINT,
            output_mint=TOKEN_MINT,
            input_amount_raw=Decimal(1000000000),
            output_amount_raw=Decimal(25000000),
            router="metis",
            mode="ultra",
            total_fee_bps=10,
            fee_mint=SOL_MINT,
            platform_fee=JupiterPlatformFee(
                amount_raw=Decimal(1000000), fee_bps=10, fee_mint=SOL_MINT
            ),
        )

        def mint_data(address, decimals):
            return VerifiedMintDecimals(
                mint=address,
                decimals=decimals,
                source="solana_rpc:getAccountInfo",
                observed_at=NOW,
                validation_status="VERIFIED",
                slot=500,
            )

        result = normalize_provider_quote(
            quote=quote,
            quote_observed_at=NOW,
            quote_currency_mint=SOL_MINT,
            input_mint_metadata=mint_data(SOL_MINT, 9),
            output_mint_metadata=mint_data(TOKEN_MINT, 6),
            fee_mint_metadata=mint_data(SOL_MINT, 9),
            input_price=None,
            fee_price=None,
            now=NOW,
            max_age=timedelta(seconds=20),
        )
        self.assertEqual(result.input_amount, Decimal(1))
        self.assertEqual(result.output_amount, Decimal(25))
        self.assertEqual(result.platform_fee_quote, Decimal("0.001"))


if __name__ == "__main__":
    unittest.main()
