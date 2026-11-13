import unittest
from datetime import timedelta

from bangzen_prime.domain.token_2022_extension_config import ParsedToken2022Configuration
from bangzen_prime.domain.token_2022_extension_evidence import Token2022ExtensionEvidence
from bangzen_prime.domain.token_2022_extensions import VERIFIED, PARTIAL, REJECTED
from bangzen_prime.domain.token_2022_risk import APPROVED, BLOCKED, HOLD, evaluate_token_2022_risk
from bangzen_prime.errors import DomainError
from bangzen_prime.errors import DomainError
from tests.support import START, TOKEN_MINT


def evidence(*, status=VERIFIED, flags=(), config_status=VERIFIED, mint=TOKEN_MINT):
    # Evidence status cannot be stronger than its configuration status.
    if config_status != VERIFIED and status == VERIFIED:
        status = config_status
    config = ParsedToken2022Configuration(config_status, (), (), tuple(flags), ())
    return Token2022ExtensionEvidence(
        mint=mint, validation_status=status, observed_at=START, source="helius",
        source_record_id="mint:slot", slot=10, risk_flags=tuple(flags), configuration=config,
    )


class Token2022RiskDecisionTests(unittest.TestCase):
    def evaluate(self, item, **kwargs):
        args = dict(expected_mint=TOKEN_MINT, now=START, max_age=timedelta(seconds=60))
        args.update(kwargs)
        return evaluate_token_2022_risk(item, **args)

    def test_verified_clean_evidence_is_eligible(self):
        result = self.evaluate(evidence())
        self.assertEqual(result.status, APPROVED)
        self.assertTrue(result.approved)

    def test_missing_partial_and_unavailable_evidence_hold(self):
        self.assertEqual(self.evaluate(None).status, HOLD)
        self.assertEqual(self.evaluate(evidence(status=PARTIAL)).status, HOLD)

    def test_rejected_evidence_blocks(self):
        self.assertEqual(self.evaluate(evidence(status=REJECTED)).status, BLOCKED)

    def test_mint_mismatch_blocks(self):
        result = self.evaluate(evidence(mint="So11111111111111111111111111111111111111112"))
        self.assertIn("TOKEN2022_MINT_MISMATCH", result.reason_codes)

    def test_stale_or_future_evidence_holds(self):
        self.assertEqual(self.evaluate(evidence(), now=START + timedelta(seconds=61)).status, HOLD)
        self.assertEqual(self.evaluate(evidence(), now=START - timedelta(seconds=1)).status, HOLD)

    def test_paused_nontransferable_and_frozen_states_veto(self):
        for flag in ("TOKEN_TRANSFERS_PAUSED", "NON_TRANSFERABLE",
                     "DEFAULT_ACCOUNTS_FROZEN", "DEFAULT_ACCOUNTS_UNINITIALIZED"):
            with self.subTest(flag=flag):
                result = self.evaluate(evidence(flags=(flag,)))
                self.assertEqual(result.status, BLOCKED)
                self.assertIn(flag, result.reason_codes)

    def test_delegate_hook_and_fee_require_review_not_automatic_ban(self):
        for flag in ("PERMANENT_DELEGATE_ACTIVE", "TRANSFER_HOOK_PROGRAM_CONFIGURED", "TRANSFER_FEE_NONZERO"):
            with self.subTest(flag=flag):
                result = self.evaluate(evidence(flags=(flag,)))
                self.assertEqual(result.status, HOLD)
                self.assertIn(flag, result.reason_codes)

    def test_partial_configuration_cannot_pass(self):
        self.assertEqual(self.evaluate(evidence(config_status=PARTIAL)).status, HOLD)

    def test_invalid_freshness_policy_rejected(self):
        with self.assertRaises(DomainError):
            self.evaluate(evidence(), max_age=timedelta(0))


if __name__ == "__main__":
    unittest.main()
