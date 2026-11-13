import base64
import json
import unittest

from bangzen_prime.errors import DomainError, ExternalServiceError
from bangzen_prime.infrastructure.adapters.chain.jupiter_v2 import JupiterSwapV2Adapter
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


class JupiterSwapV2Tests(unittest.TestCase):
    def adapter(self, recorder):
        return JupiterSwapV2Adapter(
            api_key="test-key", transport=recorder, caller=DirectCaller(), timeout=3.0
        )

    def test_order_returns_validated_unsigned_transaction(self):
        tx = base64.b64encode(b"unsigned-solana-tx").decode()
        recorder = RequestRecorder(
            [
                response(
                    {
                        "transaction": tx,
                        "requestId": "req-123",
                        "inputMint": SOL_MINT,
                        "outputMint": TOKEN_MINT,
                        "inAmount": "1000",
                        "outAmount": "25000",
                        "router": "metis",
                        "transactionVersion": 0,
                        "lastValidBlockHeight": 12345,
                    }
                )
            ]
        )
        order = self.adapter(recorder).order(
            input_mint=SOL_MINT, output_mint=TOKEN_MINT, amount=1000, taker=SOL_MINT
        )
        self.assertEqual(order.request_id, "req-123")
        self.assertEqual(order.input_amount, 1000)
        self.assertEqual(order.output_amount, 25000)
        self.assertIn("/order?", recorder.requests[0].url)
        self.assertEqual(recorder.requests[0].headers["x-api-key"], "test-key")

    def test_order_rejects_mint_mismatch(self):
        tx = base64.b64encode(b"tx").decode()
        recorder = RequestRecorder(
            [
                response(
                    {
                        "transaction": tx,
                        "requestId": "req",
                        "inputMint": TOKEN_MINT,
                        "outputMint": TOKEN_MINT,
                        "inAmount": "1000",
                        "outAmount": "2",
                        "router": "metis",
                        "transactionVersion": 0,
                    }
                )
            ]
        )
        with self.assertRaises(ExternalServiceError):
            self.adapter(recorder).order(
                input_mint=SOL_MINT, output_mint=TOKEN_MINT, amount=1000, taker=SOL_MINT
            )

    def test_execute_posts_signed_transaction_once_and_parses_result(self):
        signed = base64.b64encode(b"signed-solana-tx").decode()
        recorder = RequestRecorder(
            [
                response(
                    {
                        "status": "Success",
                        "signature": "sig-123",
                        "code": 0,
                        "totalInputAmount": "1000",
                        "totalOutputAmount": "24000",
                    }
                )
            ]
        )
        result = self.adapter(recorder).execute(
            signed_transaction_b64=signed, request_id="req-123"
        )
        self.assertEqual(result.status, "Success")
        self.assertEqual(result.signature, "sig-123")
        self.assertEqual(len(recorder.requests), 1)
        self.assertEqual(recorder.requests[0].method, "POST")
        body = json.loads(recorder.requests[0].body)
        self.assertEqual(body["requestId"], "req-123")
        self.assertEqual(body["signedTransaction"], signed)

    def test_execute_rejects_invalid_base64_before_network(self):
        recorder = RequestRecorder([])
        with self.assertRaises(DomainError):
            self.adapter(recorder).execute(
                signed_transaction_b64="not base64!", request_id="req"
            )
        self.assertEqual(recorder.requests, [])

    def test_execute_rejects_incomplete_success_response(self):
        signed = base64.b64encode(b"signed-solana-tx").decode()
        recorder = RequestRecorder(
            [
                response(
                    {
                        "status": "Success",
                        "code": 0,
                        "totalInputAmount": "1",
                        "totalOutputAmount": "2",
                    }
                )
            ]
        )
        with self.assertRaises(ExternalServiceError):
            self.adapter(recorder).execute(
                signed_transaction_b64=signed, request_id="req"
            )


if __name__ == "__main__":
    unittest.main()
