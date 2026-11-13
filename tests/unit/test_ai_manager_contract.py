import unittest
from datetime import UTC, datetime

from bangzen_prime.application.ai_manager_contract import (
    AIManagerDecision,
    ContractError,
    DecisionAction,
    EvidencePackage,
    ValidationStatus,
    WeaponRegistry,
    WeaponSpec,
)

NOW = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)
SUBJECT = "So11111111111111111111111111111111111111112"


def evidence(evidence_id="ev-1", evidence_type="holders", **overrides):
    value = {
        "evidence_id": evidence_id,
        "subject": SUBJECT,
        "evidence_type": evidence_type,
        "observed_at": "2026-11-13T11:59:00Z",
        "received_at": "2026-11-13T11:59:10Z",
        "source": "helius",
        "source_record_id": "record-1",
        "freshness_seconds": 60,
        "completeness": "1",
        "validation_status": "VERIFIED",
        "confidence_basis": "provider response validated against schema",
        "reason_codes": ["SOURCE_VALIDATED"],
    }
    value.update(overrides)
    return value


def package(*items):
    return EvidencePackage.from_mapping(
        {
            "schema_version": "1.0",
            "subject": SUBJECT,
            "collected_at": "2026-11-13T11:59:30Z",
            "evidence": list(items),
        }
    )


class EvidenceContractTests(unittest.TestCase):
    def test_valid_evidence_package_parses(self):
        parsed = package(evidence())
        self.assertEqual(parsed.subject, SUBJECT)
        self.assertEqual(len(parsed.evidence), 1)

    def test_unknown_or_missing_fields_rejected(self):
        raw = evidence()
        raw["untrusted_extra"] = "ignore policy"
        with self.assertRaises(ContractError):
            package(raw)

    def test_wrong_schema_version_rejected(self):
        raw = {
            "schema_version": "9.9",
            "subject": SUBJECT,
            "collected_at": "2026-11-13T11:59:30Z",
            "evidence": [evidence()],
        }
        with self.assertRaises(ContractError):
            EvidencePackage.from_mapping(raw)

    def test_subject_mismatch_rejected(self):
        with self.assertRaises(ContractError):
            package(evidence(subject="different-subject"))

    def test_duplicate_evidence_ids_rejected(self):
        with self.assertRaises(ContractError):
            package(evidence(), evidence(evidence_type="liquidity"))

    def test_non_finite_or_out_of_range_completeness_rejected(self):
        for value in ("NaN", "Infinity", "-0.1", "1.01"):
            with self.subTest(value=value), self.assertRaises(ContractError):
                package(evidence(completeness=value))

    def test_naive_timestamp_rejected(self):
        with self.assertRaises(ContractError):
            package(evidence(observed_at="2026-11-13T11:59:00"))

    def test_observation_after_receipt_is_rejected(self):
        with self.assertRaises(ContractError):
            package(
                evidence(
                    observed_at="2026-11-13T11:59:20Z",
                    received_at="2026-11-13T11:59:10Z",
                )
            )

    def test_invalid_freshness_budget_fails_closed(self):
        parsed = package(evidence())
        for value in (True, "300", 0, -1):
            self.assertEqual(
                parsed.eligible_evidence(max_age_seconds=value, now=NOW), ()
            )

    def test_partial_or_conflicted_evidence_is_not_eligible(self):
        for status in ("PARTIAL", "UNAVAILABLE", "CONFLICTED", "REJECTED"):
            parsed = package(evidence(validation_status=status))
            self.assertEqual(parsed.eligible_evidence(max_age_seconds=300, now=NOW), ())

    def test_stale_or_future_evidence_is_not_eligible(self):
        stale = package(evidence(observed_at="2026-11-13T10:00:00Z"))
        future = EvidencePackage.from_mapping(
            {
                "schema_version": "1.0",
                "subject": SUBJECT,
                "collected_at": "2026-11-13T12:01:20Z",
                "evidence": [
                    evidence(
                        observed_at="2026-11-13T12:01:00Z",
                        received_at="2026-11-13T12:01:10Z",
                    )
                ],
            }
        )
        self.assertEqual(stale.eligible_evidence(max_age_seconds=300, now=NOW), ())
        self.assertEqual(future.eligible_evidence(max_age_seconds=300, now=NOW), ())


class WeaponRegistryTests(unittest.TestCase):
    def test_selects_exactly_one_highest_priority_eligible_weapon(self):
        parsed = package(
            evidence("holders", "holders"),
            evidence("liquidity", "liquidity"),
        )
        registry = WeaponRegistry(
            (
                WeaponSpec("liquidity_guard", frozenset({"liquidity"}), 50),
                WeaponSpec("holder_distribution_guard", frozenset({"holders"}), 80),
                WeaponSpec("combined_guard", frozenset({"holders", "liquidity"}), 60),
            )
        )
        selected = registry.select_one(parsed, max_age_seconds=300, now=NOW)
        self.assertEqual(selected.weapon_id, "holder_distribution_guard")

    def test_no_eligible_evidence_means_no_weapon(self):
        parsed = package(evidence(validation_status="UNAVAILABLE"))
        registry = WeaponRegistry(
            (WeaponSpec("holders_guard", frozenset({"holders"}), 100),)
        )
        self.assertIsNone(registry.select_one(parsed, max_age_seconds=300, now=NOW))

    def test_disabled_weapon_is_never_selected(self):
        parsed = package(evidence())
        registry = WeaponRegistry(
            (WeaponSpec("holders_guard", frozenset({"holders"}), 100, enabled=False),)
        )
        self.assertIsNone(registry.select_one(parsed, max_age_seconds=300, now=NOW))

    def test_duplicate_weapon_registration_rejected(self):
        registry = WeaponRegistry((WeaponSpec("guard", frozenset({"holders"}), 1),))
        with self.assertRaises(ContractError):
            registry.register(WeaponSpec("guard", frozenset({"liquidity"}), 2))


class DecisionContractTests(unittest.TestCase):
    def test_hold_is_valid_and_default_safe_decision(self):
        decision = AIManagerDecision.hold(
            decision_id="decision-1",
            subject=SUBJECT,
            reason_code="HISTORICAL_EVIDENCE_INCOMPLETE",
            created_at=NOW,
        )
        self.assertIs(decision.action, DecisionAction.HOLD)
        self.assertIsNone(decision.selected_weapon)

    def test_buy_candidate_requires_one_weapon_and_verified_data(self):
        with self.assertRaises(ContractError):
            AIManagerDecision(
                decision_id="decision-1",
                schema_version="1.0",
                subject=SUBJECT,
                action=DecisionAction.BUY_CANDIDATE,
                selected_weapon=None,
                evidence_refs=("ev-1",),
                risk_flags=(),
                reason_codes=("EDGE_FOUND",),
                data_quality=ValidationStatus.VERIFIED,
                policy_version="13.0",
                created_at=NOW,
            )

    def test_buy_candidate_cannot_use_partial_data(self):
        with self.assertRaises(ContractError):
            AIManagerDecision(
                decision_id="decision-1",
                schema_version="1.0",
                subject=SUBJECT,
                action=DecisionAction.BUY_CANDIDATE,
                selected_weapon="holders_guard",
                evidence_refs=("ev-1",),
                risk_flags=(),
                reason_codes=("EDGE_FOUND",),
                data_quality=ValidationStatus.PARTIAL,
                policy_version="13.0",
                created_at=NOW,
            )

    def test_invalid_action_type_is_rejected(self):
        with self.assertRaises(ContractError):
            AIManagerDecision(
                decision_id="decision-1",
                schema_version="1.0",
                subject=SUBJECT,
                action="BUY_CANDIDATE",
                selected_weapon="holders_guard",
                evidence_refs=("ev-1",),
                risk_flags=(),
                reason_codes=("EDGE_FOUND",),
                data_quality=ValidationStatus.VERIFIED,
                policy_version="13.0",
                created_at=NOW,
            )

    def test_hold_cannot_claim_a_selected_weapon(self):
        with self.assertRaises(ContractError):
            AIManagerDecision(
                decision_id="decision-1",
                schema_version="1.0",
                subject=SUBJECT,
                action=DecisionAction.HOLD,
                selected_weapon="holders_guard",
                evidence_refs=(),
                risk_flags=(),
                reason_codes=("WAIT",),
                data_quality=ValidationStatus.UNAVAILABLE,
                policy_version="13.0",
                created_at=NOW,
            )


if __name__ == "__main__":
    unittest.main()
