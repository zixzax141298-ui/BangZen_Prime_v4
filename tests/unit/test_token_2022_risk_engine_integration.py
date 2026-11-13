import unittest
import uuid
from decimal import Decimal

from bangzen_prime.application.risk_engine import RiskEngine, RiskLimits, TradeRequest
from bangzen_prime.domain.risk import PortfolioSnapshot
from bangzen_prime.domain.signals import PriceLevels
from bangzen_prime.domain.token_2022_extension_config import (
    ParsedToken2022Configuration,
)
from bangzen_prime.domain.token_2022_extension_evidence import (
    Token2022ExtensionEvidence,
)
from bangzen_prime.domain.token_2022_extensions import VERIFIED
from bangzen_prime.domain.token_programs import TOKEN_2022_PROGRAM_ID, TOKEN_PROGRAM_ID
from tests.support import START, TOKEN_MINT

D = Decimal
TOKEN_2022 = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"


def risk_engine():
    return RiskEngine(
        RiskLimits(
            max_risk_per_trade_pct=D(1),
            max_open_positions=3,
            max_exposure_quote=D(500),
            max_drawdown_pct=D(20),
            min_liquidity_usd=D(10000),
            max_spread_pct=D(1),
            max_slippage_pct=D(1),
            fee_rate=D("0.001"),
        )
    )


def request():
    return TradeRequest(
        signal_id=uuid.uuid4(),
        token_id=uuid.uuid4(),
        token_mint=TOKEN_MINT,
        levels=PriceLevels(D(2), D("1.8"), D("2.3")),
        liquidity_usd=D(50000),
        spread_pct=D(0),
        slippage_pct=D("0.5"),
        token_program=TOKEN_2022,
    )


def portfolio():
    return PortfolioSnapshot.create(
        equity_quote="1000",
        peak_equity_quote="1000",
        open_positions=(),
        as_of=START,
    )


def evidence(flags=()):
    config = ParsedToken2022Configuration(VERIFIED, (), (), tuple(flags), ())
    return Token2022ExtensionEvidence(
        mint=TOKEN_MINT,
        validation_status=VERIFIED,
        observed_at=START,
        source="helius",
        source_record_id="mint:slot",
        slot=100,
        risk_flags=tuple(flags),
        configuration=config,
        token_program=TOKEN_2022_PROGRAM_ID,
    )


class Token2022RiskEngineIntegrationTests(unittest.TestCase):
    def test_token_2022_request_without_evidence_is_vetoed(self):
        decision = risk_engine().evaluate(request(), portfolio(), START)
        self.assertFalse(decision.approved)
        self.assertIn("TOKEN2022_EVIDENCE_UNAVAILABLE", decision.reasons)

    def test_token_2022_request_with_verified_clean_evidence_can_pass_this_gate(self):
        decision = risk_engine().evaluate(
            request(), portfolio(), START, token_program_evidence=evidence()
        )
        self.assertTrue(decision.approved)

    def test_token_2022_hard_veto_reaches_risk_engine(self):
        decision = risk_engine().evaluate(
            request(),
            portfolio(),
            START,
            token_program_evidence=evidence(("TOKEN_TRANSFERS_PAUSED",)),
        )
        self.assertFalse(decision.approved)
        self.assertIn("TOKEN2022_HARD_VETO", decision.reasons)
        self.assertIn("TOKEN_TRANSFERS_PAUSED", decision.reasons)

    def test_token_2022_review_flag_holds_without_mislabeling_as_malicious(self):
        decision = risk_engine().evaluate(
            request(),
            portfolio(),
            START,
            token_program_evidence=evidence(("PERMANENT_DELEGATE_ACTIVE",)),
        )
        self.assertFalse(decision.approved)
        self.assertIn("TOKEN2022_REVIEW_REQUIRED", decision.reasons)

    def test_classic_program_id_without_mint_owner_evidence_is_vetoed(self):
        classic = TradeRequest(
            signal_id=uuid.uuid4(),
            token_id=uuid.uuid4(),
            token_mint=TOKEN_MINT,
            levels=PriceLevels(D(2), D("1.8"), D("2.3")),
            liquidity_usd=D(50000),
            spread_pct=D(0),
            slippage_pct=D("0.5"),
            token_program=TOKEN_PROGRAM_ID,
        )
        decision = risk_engine().evaluate(classic, portfolio(), START)
        self.assertFalse(decision.approved)
        self.assertIn("TOKEN_PROGRAM_EVIDENCE_UNAVAILABLE", decision.reasons)

    def test_classic_program_id_with_unconfirmed_owner_evidence_is_vetoed(self):
        classic = TradeRequest(
            signal_id=uuid.uuid4(),
            token_id=uuid.uuid4(),
            token_mint=TOKEN_MINT,
            levels=PriceLevels(D(2), D("1.8"), D("2.3")),
            liquidity_usd=D(50000),
            spread_pct=D(0),
            slippage_pct=D("0.5"),
            token_program=TOKEN_PROGRAM_ID,
        )
        forged = Token2022ExtensionEvidence(
            mint=TOKEN_MINT,
            validation_status="REJECTED",
            observed_at=START,
            source="helius",
            source_record_id="not-a-mint",
            slot=10,
            token_program=TOKEN_PROGRAM_ID,
            account_data_length=165,
            reason_codes=("UNSUPPORTED_MINT_OWNER_PROGRAM",),
        )
        decision = risk_engine().evaluate(
            classic, portfolio(), START, token_program_evidence=forged
        )
        self.assertFalse(decision.approved)
        self.assertIn("TOKEN_PROGRAM_EVIDENCE_INVALID", decision.reasons)

    def test_unknown_token_program_is_fail_closed(self):
        unknown = TradeRequest(
            signal_id=uuid.uuid4(),
            token_id=uuid.uuid4(),
            token_mint=TOKEN_MINT,
            levels=PriceLevels(D(2), D("1.8"), D("2.3")),
            liquidity_usd=D(50000),
            spread_pct=D(0),
            slippage_pct=D("0.5"),
            token_program="UnknownTokenProgram111111111111111111111111111",
        )
        decision = risk_engine().evaluate(unknown, portfolio(), START)
        self.assertFalse(decision.approved)
        self.assertIn("UNSUPPORTED_TOKEN_PROGRAM", decision.reasons)

    def test_classic_token_path_is_backward_compatible(self):
        classic = TradeRequest(
            signal_id=uuid.uuid4(),
            token_id=uuid.uuid4(),
            token_mint=TOKEN_MINT,
            levels=PriceLevels(D(2), D("1.8"), D("2.3")),
            liquidity_usd=D(50000),
            spread_pct=D(0),
            slippage_pct=D("0.5"),
            token_program=TOKEN_PROGRAM_ID,
        )
        classic_evidence = Token2022ExtensionEvidence(
            mint=TOKEN_MINT,
            validation_status="REJECTED",
            observed_at=START,
            source="helius",
            source_record_id="classic-mint",
            slot=10,
            token_program=TOKEN_PROGRAM_ID,
            account_data_length=82,
            reason_codes=("CLASSIC_SPL_MINT_CONFIRMED",),
        )
        self.assertTrue(
            risk_engine()
            .evaluate(
                classic, portfolio(), START, token_program_evidence=classic_evidence
            )
            .approved
        )


if __name__ == "__main__":
    unittest.main()
