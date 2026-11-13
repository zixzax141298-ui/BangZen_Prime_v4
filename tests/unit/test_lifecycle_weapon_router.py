from datetime import datetime, timezone
import json
import os
import tempfile
import unittest

from bangzen_prime.application.ai_manager_contract import EvidencePackage
from bangzen_prime.application.lifecycle_weapon_router import (
    ANALYSIS_ONLY_WEAPONS,
    PHASES,
    LifecycleWeaponSelector,
    load_policy,
    policy_from_mapping,
)
from bangzen_prime.errors import ConfigurationError


NOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)
SUBJECT = "So11111111111111111111111111111111111111112"


def record(evidence_id, evidence_type, **overrides):
    raw = {
        "evidence_id": evidence_id,
        "subject": SUBJECT,
        "evidence_type": evidence_type,
        "observed_at": "2026-11-13T11:59:00Z",
        "received_at": "2026-11-13T11:59:10Z",
        "source": "helius",
        "source_record_id": evidence_id,
        "freshness_seconds": 60,
        "completeness": "1",
        "validation_status": "VERIFIED",
        "confidence_basis": "validated source record and schema",
        "reason_codes": ["SOURCE_VALIDATED"],
    }
    raw.update(overrides)
    return raw


def package(*records):
    return EvidencePackage.from_mapping({
        "schema_version": "1.0",
        "subject": SUBJECT,
        "collected_at": "2026-11-13T11:59:30Z",
        "evidence": list(records),
    })


def default_selector():
    path = os.path.join(
        os.path.dirname(__file__), "..", "..", "config",
        "lifecycle_weapon_policy.json",
    )
    return LifecycleWeaponSelector(load_policy(path))


class LifecycleWeaponSelectionTests(unittest.TestCase):
    def test_each_lifecycle_phase_is_declared(self):
        selector = default_selector()
        self.assertEqual(set(selector._policy.phases), PHASES)

    def test_launch_selects_bundle_detector_when_its_evidence_exists(self):
        evidence = package(
            record("launch-1", "launch_transactions"),
            record("funding-1", "funding_graph"),
            record("holders-1", "holder_distribution"),
        )
        plan = default_selector().select(
            "PUMPFUN_LAUNCH", evidence, max_age_seconds=300, now=NOW
        )
        self.assertEqual(plan.selected_weapon, "sequential_bundle_detector")
        self.assertEqual(plan.evidence_refs, ("funding-1", "launch-1"))
        self.assertFalse(plan.execution_authorized)

    def test_migration_prefers_pool_integrity_weapon_only_with_complete_evidence(self):
        evidence = package(
            record("migration-1", "migration_event"),
            record("pool-1", "pool_state"),
            record("liq-1", "liquidity_snapshot"),
            record("curve-1", "curve_state"),
            record("flow-1", "swap_flow"),
        )
        plan = default_selector().select(
            "MIGRATION", evidence, max_age_seconds=300, now=NOW
        )
        self.assertEqual(plan.selected_weapon, "lp_sniper_adapter")
        self.assertEqual(plan.evidence_refs, ("liq-1", "migration-1", "pool-1"))

    def test_distribution_prefers_downside_radar(self):
        evidence = package(
            record("liq-1", "liquidity_snapshot"),
            record("flow-1", "swap_flow"),
            record("dev-1", "dev_wallet_flow"),
            record("wallet-1", "wallet_flow"),
        )
        plan = default_selector().select(
            "DISTRIBUTION", evidence, max_age_seconds=300, now=NOW
        )
        self.assertEqual(plan.selected_weapon, "pre_dump_radar")

    def test_only_one_weapon_can_be_selected(self):
        evidence = package(
            record("liq-1", "liquidity_snapshot"),
            record("migration-1", "migration_event"),
            record("pool-1", "pool_state"),
            record("lp-1", "lp_ownership"),
        )
        plan = default_selector().select(
            "RAYDIUM_POOL", evidence, max_age_seconds=300, now=NOW
        )
        self.assertIn(plan.selected_weapon, ANALYSIS_ONLY_WEAPONS)
        self.assertEqual(plan.max_selected_weapons, 1)

    def test_stale_partial_or_unavailable_evidence_selects_nothing(self):
        cases = (
            record("old", "launch_transactions", observed_at="2026-11-13T10:00:00Z"),
            record("partial", "launch_transactions", validation_status="PARTIAL"),
            record("unavailable", "launch_transactions", validation_status="UNAVAILABLE"),
        )
        for item in cases:
            evidence = package(
                item,
                record("funding", "funding_graph"),
            )
            plan = default_selector().select(
                "PUMPFUN_LAUNCH", evidence, max_age_seconds=300, now=NOW
            )
            self.assertIsNone(plan.selected_weapon)

    def test_missing_required_evidence_never_forces_a_weapon(self):
        evidence = package(record("only-one", "launch_transactions"))
        plan = default_selector().select(
            "PUMPFUN_LAUNCH", evidence, max_age_seconds=300, now=NOW
        )
        self.assertIsNone(plan.selected_weapon)
        self.assertEqual(plan.reason_code, "NO_RELEVANT_WEAPON_OR_EVIDENCE")

    def test_unknown_phase_fails_closed(self):
        evidence = package(record("launch", "launch_transactions"))
        plan = default_selector().select(
            "UNRECOGNIZED", evidence, max_age_seconds=300, now=NOW
        )
        self.assertIsNone(plan.selected_weapon)
        self.assertEqual(plan.reason_code, "UNKNOWN_OR_UNVERIFIED_PHASE")

    def test_execution_weapon_is_rejected_by_policy(self):
        with open(os.path.join(os.path.dirname(__file__), "..", "..", "config",
                               "lifecycle_weapon_policy.json"), encoding="utf-8") as fh:
            raw = json.load(fh)
        raw["phases"]["GROWTH"].append({
            "weapon_id": "jito_adapter",
            "required_evidence": ["wallet_flow"],
            "priority": 1000,
        })
        with self.assertRaises(ConfigurationError):
            policy_from_mapping(raw)

    def test_policy_cannot_select_multiple_or_omit_phase(self):
        with open(os.path.join(os.path.dirname(__file__), "..", "..", "config",
                               "lifecycle_weapon_policy.json"), encoding="utf-8") as fh:
            raw = json.load(fh)
        raw["max_selected_weapons"] = 2
        with self.assertRaises(ConfigurationError):
            policy_from_mapping(raw)
        raw["max_selected_weapons"] = 1
        del raw["phases"]["REVIVAL"]
        with self.assertRaises(ConfigurationError):
            policy_from_mapping(raw)

    def test_policy_rejects_boolean_and_float_weapon_limits(self):
        with open(os.path.join(os.path.dirname(__file__), "..", "..", "config",
                               "lifecycle_weapon_policy.json"), encoding="utf-8") as fh:
            raw = json.load(fh)
        for invalid in (True, 1.0, 0, 2):
            raw["max_selected_weapons"] = invalid
            with self.subTest(invalid=invalid), self.assertRaises(ConfigurationError):
                policy_from_mapping(raw)

    def test_bad_policy_file_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "policy.json")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("{broken")
            with self.assertRaises(ConfigurationError):
                load_policy(path)


if __name__ == "__main__":
    unittest.main()
