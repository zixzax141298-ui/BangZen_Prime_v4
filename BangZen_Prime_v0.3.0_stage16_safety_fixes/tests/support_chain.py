"""Chain fakes for tests only. None of these touch a network, a key, or a real chain."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from bangzen_prime.core.errors import ExternalServiceError
from bangzen_prime.core.ports import SignedTransaction, SimulationResult
from bangzen_prime.execution.execution import PlannedTransaction, Quote, Transfer
from tests.support import SOL_MINT, START, TOKEN_MINT

OWNER = "OwnerWallet1111111111111111111111111111111"
PROGRAM = "RouteProgram11111111111111111111111111111"
PROVIDER = "jupiter-compatible"
VAULT = "VaultAccount1111111111111111111111111111111"


class FakeQuotes:
    def __init__(
        self,
        *,
        provider=PROVIDER,
        impact="0.5",
        out="50",
        ttl=30,
        fail=False,
        in_amount_override=None,
    ):
        self.provider, self.impact, self.out, self.ttl = provider, impact, out, ttl
        self.fail, self.override = fail, in_amount_override
        self.now = START

    def quote(self, input_mint, output_mint, in_amount):
        if self.fail:
            raise ExternalServiceError("quote down", service="quote", retryable=True)
        return Quote.create(
            provider=self.provider,
            input_mint=input_mint,
            output_mint=output_mint,
            in_amount=self.override or in_amount,
            out_amount=self.out,
            price_impact_pct=self.impact,
            quoted_at=self.now,
            expires_at=self.now + timedelta(seconds=self.ttl),
        )


class FakeBuilder:
    def __init__(
        self,
        *,
        programs=(PROGRAM,),
        destination=VAULT,
        spend=None,
        fee_payer=OWNER,
        source=OWNER,
        ttl=120,
    ):
        self.programs, self.destination, self.spend = programs, destination, spend
        self.fee_payer, self.source, self.ttl = fee_payer, source, ttl
        self.now = START

    def build(self, quote):
        amount = self.spend if self.spend is not None else quote.in_amount
        return PlannedTransaction(
            provider=quote.provider,
            program_ids=tuple(self.programs),
            transfers=(
                Transfer(quote.input_mint, amount, self.source, self.destination),
            ),
            fee_payer=self.fee_payer,
            expires_at=self.now + timedelta(seconds=self.ttl),
        )


class FakeRpc:
    def __init__(
        self,
        *,
        simulate_error=None,
        sim_down=False,
        status_seq=("CONFIRMED",),
        send_fails=False,
    ):
        self.simulate_error = simulate_error
        self.sim_down = sim_down
        self.status_seq = list(status_seq)
        self.send_fails = send_fails
        self.sent: list[SignedTransaction] = []
        self.polls = 0
        self.balances = {}

    def simulate(self, plan):
        if self.sim_down:
            raise ExternalServiceError("rpc down", service="rpc", retryable=True)
        if self.simulate_error:
            return SimulationResult(False, self.simulate_error)
        return SimulationResult(True)

    def send(self, signed):
        if self.send_fails:
            raise ExternalServiceError("send timed out", service="rpc", retryable=True)
        self.sent.append(signed)
        return "SIG" + str(len(self.sent))

    def signature_status(self, signature):
        self.polls += 1
        idx = min(self.polls - 1, len(self.status_seq) - 1)
        return self.status_seq[idx]

    def token_balance(self, owner, mint):
        return self.balances.get((owner, mint), Decimal(0))


class FakeSigner:
    """Test-only signer. Produces a signed object without key material. Never used in production."""

    def __init__(self):
        self.calls = 0

    def sign(self, plan):
        self.calls += 1
        return SignedTransaction(raw=b"test-only", plan=plan)


MINTS = dict(input_mint=SOL_MINT, output_mint=TOKEN_MINT)
