import unittest
from datetime import timedelta

from bangzen_prime.application.token_program_evidence import TokenProgramEvidenceUseCase
from bangzen_prime.domain.token_2022_extension_config import (
    ParsedToken2022Configuration,
)
from bangzen_prime.domain.token_2022_extension_evidence import (
    Token2022ExtensionEvidence,
)
from bangzen_prime.domain.token_2022_extensions import REJECTED, VERIFIED
from bangzen_prime.domain.token_2022_risk import APPROVED, BLOCKED, HOLD
from bangzen_prime.domain.token_programs import TOKEN_2022_PROGRAM_ID, TOKEN_PROGRAM_ID
from tests.support import START, TOKEN_MINT


def make_evidence(
    *,
    owner=TOKEN_2022_PROGRAM_ID,
    status=VERIFIED,
    flags=(),
    reason_codes=(),
    mint=TOKEN_MINT,
    config_status=VERIFIED,
    observed_at=START,
):
    config = ParsedToken2022Configuration(config_status, (), (), tuple(flags), ())
    return Token2022ExtensionEvidence(
        mint=mint,
        validation_status=status,
        observed_at=observed_at,
        source="helius",
        source_record_id="account-info:slot-10",
        slot=10,
        token_program=owner,
        account_data_length=82 if owner == TOKEN_PROGRAM_ID else None,
        risk_flags=tuple(flags),
        reason_codes=tuple(reason_codes),
        configuration=config,
    )


class FakeReader:
    def __init__(self, evidence=None, error=None):
        self.evidence = evidence
        self.error = error
        self.calls = []

    def read(self, mint):
        self.calls.append(mint)
        if self.error:
            raise self.error
        return self.evidence


class TokenProgramEvidenceUseCaseTests(unittest.TestCase):
    def audit(self, reader):
        return TokenProgramEvidenceUseCase(reader).execute(
            TOKEN_MINT, now=START, max_age=timedelta(seconds=60)
        )

    def test_classic_spl_owner_is_explicitly_not_applicable(self):
        item = make_evidence(
            owner=TOKEN_PROGRAM_ID,
            status=REJECTED,
            reason_codes=("CLASSIC_SPL_MINT_CONFIRMED",),
        )
        result = self.audit(FakeReader(item))
        self.assertTrue(result.approved)
        self.assertEqual(result.token_program, TOKEN_PROGRAM_ID)
        self.assertEqual(result.status, "NOT_APPLICABLE")

    def test_token_2022_clean_verified_evidence_is_approved(self):
        result = self.audit(FakeReader(make_evidence()))
        self.assertEqual(result.status, APPROVED)
        self.assertTrue(result.approved)

    def test_token_2022_hard_veto_blocks(self):
        result = self.audit(
            FakeReader(make_evidence(flags=("TOKEN_TRANSFERS_PAUSED",)))
        )
        self.assertEqual(result.status, BLOCKED)
        self.assertIn("TOKEN2022_HARD_VETO", result.reason_codes)

    def test_token_2022_review_feature_holds(self):
        result = self.audit(
            FakeReader(make_evidence(flags=("PERMANENT_DELEGATE_ACTIVE",)))
        )
        self.assertEqual(result.status, HOLD)
        self.assertIn("TOKEN2022_REVIEW_REQUIRED", result.reason_codes)

    def test_missing_reader_provider_error_and_wrong_mint_hold_or_block(self):
        self.assertEqual(self.audit(None).status, HOLD)
        self.assertEqual(
            self.audit(FakeReader(error=RuntimeError("secret"))).status, HOLD
        )
        wrong = make_evidence(mint="So11111111111111111111111111111111111111112")
        self.assertEqual(self.audit(FakeReader(wrong)).status, BLOCKED)

    def test_stale_classic_owner_evidence_does_not_bypass_freshness(self):
        stale = make_evidence(
            owner=TOKEN_PROGRAM_ID,
            status=REJECTED,
            reason_codes=("CLASSIC_SPL_MINT_CONFIRMED",),
            observed_at=START - timedelta(seconds=61),
        )
        result = self.audit(FakeReader(stale))
        self.assertEqual(result.status, HOLD)
        self.assertIn("TOKEN_PROGRAM_EVIDENCE_STALE", result.reason_codes)

    def test_unknown_program_owner_is_blocked(self):
        unknown = make_evidence(owner="UnknownProgram111111111111111111111111111111")
        self.assertEqual(self.audit(FakeReader(unknown)).status, BLOCKED)

    def test_partial_configuration_does_not_pass(self):
        partial = make_evidence(status="PARTIAL", config_status="PARTIAL")
        self.assertEqual(self.audit(FakeReader(partial)).status, HOLD)


if __name__ == "__main__":
    unittest.main()
