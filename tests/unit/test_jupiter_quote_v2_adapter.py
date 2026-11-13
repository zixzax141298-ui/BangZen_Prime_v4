import json
import unittest
from decimal import Decimal

from bangzen_prime.errors import DomainError, ExternalServiceError
from bangzen_prime.infrastructure.adapters.chain.jupiter_quote_v2 import (
    JupiterQuoteV2Adapter,
)
from bangzen_prime.infrastructure.http import HttpResponse
from tests.support import SOL_MINT, TOKEN_MINT


class DirectCaller:
    def call(self, operation):
        return operation()


class RequestRecorder:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def response(payload, status=200):
    return HttpResponse(status, json.dumps(payload).encode(), {})


class JupiterQuoteV2Tests(unittest.TestCase):
    def adapter(self, recorder):
        return JupiterQuoteV2Adapter(
            api_key="test-key", transport=recorder, caller=DirectCaller(), timeout=3.0
        )

    def payload(self, **overrides):
        data = {
            "transaction": None,
            "requestId": "quote-123",
            "inputMint": SOL_MINT,
            "outputMint": TOKEN_MINT,
            "inAmount": "1000000000",
            "outAmount": "25000000",
            "router": "metis",
            "mode": "ultra",
            "feeBps": 12,
            "feeMint": SOL_MINT,
            "platformFee": {
                "amount": "1000000",
                "feeBps": 10,
            },
        }
        data.update(overrides)
        return data

    def test_quote_uses_order_endpoint_without_taker_or_transaction(self):
        recorder = RequestRecorder([response(self.payload())])
        quote = self.adapter(recorder).quote(
            input_mint=SOL_MINT, output_mint=TOKEN_MINT, amount=1_000_000_000
        )
        request = recorder.requests[0]
        self.assertIn("/order?", request.url)
        self.assertNotIn("taker=", request.url)
        self.assertEqual(request.headers["x-api-key"], "test-key")
        self.assertEqual(quote.input_amount_raw, Decimal(1000000000))
        self.assertEqual(quote.output_amount_raw, Decimal(25000000))
        self.assertEqual(quote.total_fee_bps, 12)
        self.assertEqual(quote.platform_fee.amount_raw, Decimal(1000000))

    def test_quote_accepts_empty_transaction_quote_only_response(self):
        recorder = RequestRecorder([response(self.payload(transaction=""))])
        quote = self.adapter(recorder).quote(
            input_mint=SOL_MINT, output_mint=TOKEN_MINT, amount=1_000_000_000
        )
        self.assertEqual(quote.output_amount_raw, Decimal(25000000))

    def test_quote_rejects_transaction_payload(self):
        recorder = RequestRecorder([response(self.payload(transaction="unsigned-tx"))])
        with self.assertRaises(ExternalServiceError):
            self.adapter(recorder).quote(
                input_mint=SOL_MINT, output_mint=TOKEN_MINT, amount=1_000_000_000
            )

    def test_quote_rejects_wrong_mints_and_amounts(self):
        cases = [
            {"inputMint": TOKEN_MINT},
            {"inAmount": "999"},
            {"outAmount": "0"},
        ]
        for changes in cases:
            with self.subTest(changes=changes):
                recorder = RequestRecorder([response(self.payload(**changes))])
                with self.assertRaises(ExternalServiceError):
                    self.adapter(recorder).quote(
                        input_mint=SOL_MINT,
                        output_mint=TOKEN_MINT,
                        amount=1_000_000_000,
                    )

    def test_quote_rejects_invalid_fee_metadata(self):
        for changes in ({"feeBps": True}, {"feeBps": 10001}, {"feeMint": "bad-mint"}):
            with self.subTest(changes=changes):
                recorder = RequestRecorder([response(self.payload(**changes))])
                with self.assertRaises(ExternalServiceError):
                    self.adapter(recorder).quote(
                        input_mint=SOL_MINT,
                        output_mint=TOKEN_MINT,
                        amount=1_000_000_000,
                    )

    def test_quote_rejects_malformed_platform_fee(self):
        recorder = RequestRecorder(
            [response(self.payload(platformFee={"amount": "NaN"}))]
        )
        with self.assertRaises(ExternalServiceError):
            self.adapter(recorder).quote(
                input_mint=SOL_MINT, output_mint=TOKEN_MINT, amount=1_000_000_000
            )

    def test_invalid_amount_fails_before_network(self):
        recorder = RequestRecorder([])
        with self.assertRaises(DomainError):
            self.adapter(recorder).quote(
                input_mint=SOL_MINT, output_mint=TOKEN_MINT, amount=True
            )
        self.assertEqual(recorder.requests, [])


if __name__ == "__main__":
    unittest.main()
