"""Unit tests for the phase policy. Pure logic, no network, no sockets."""

from __future__ import annotations

import json
import os
import tempfile
import unittest

from bangzen_prime.application.phase_policy import (
    DEFAULT_POLICY, PHASES, Action, Evidence, PhasePolicy, PhaseRule,
    load_policy, policy_from_dict,
)
from bangzen_prime.errors import ConfigurationError

ALL = Evidence(safety=True, holders=True, liquidity=True, volume=True, ai=True, intel=True)
NONE = Evidence(safety=False, holders=False, liquidity=False, volume=False, ai=False, intel=False)


def _ev(**kw) -> Evidence:
    base = {"safety": True, "holders": True, "liquidity": True, "volume": True, "ai": True, "intel": True}
    base.update(kw)
    return Evidence(**base)


class DefaultPolicyBehaviourTests(unittest.TestCase):
    def test_unknown_and_launch_are_watch_only_even_with_full_evidence(self):
        for phase in ("UNKNOWN", "LAUNCH", "CEX_LISTED"):
            with self.subTest(phase=phase):
                self.assertIs(DEFAULT_POLICY.evaluate(phase, ALL).action, Action.WATCH)

    def test_entry_phases_enter_only_with_complete_evidence(self):
        for phase in ("EARLY", "GROWTH", "MATURE"):
            with self.subTest(phase=phase):
                self.assertIs(DEFAULT_POLICY.evaluate(phase, ALL).action, Action.ENTER_PAPER)

    def test_any_missing_required_evidence_rejects(self):
        verdict = DEFAULT_POLICY.evaluate("GROWTH", _ev(intel=False))
        self.assertIs(verdict.action, Action.REJECT)
        self.assertEqual(verdict.missing, ("intel",))

    def test_missing_ai_blocks_entry_even_when_everything_else_passes(self):
        # Without a model verdict there is no BUY evidence, so no paper entry.
        self.assertIs(DEFAULT_POLICY.evaluate("EARLY", _ev(ai=False)).action, Action.REJECT)

    def test_checks_not_required_by_phase_are_not_demanded(self):
        # EARLY does not require volume: missing volume must not block it.
        self.assertIs(DEFAULT_POLICY.evaluate("EARLY", _ev(volume=False)).action, Action.ENTER_PAPER)
        self.assertNotIn("volume", DEFAULT_POLICY.required_checks("EARLY"))

    def test_no_evidence_never_enters(self):
        for phase in PHASES:
            with self.subTest(phase=phase):
                self.assertIsNot(DEFAULT_POLICY.evaluate(phase, NONE).action, Action.ENTER_PAPER)

    def test_unknown_phase_name_is_rejected_not_crashed(self):
        verdict = DEFAULT_POLICY.evaluate("NOT_A_PHASE", ALL)
        self.assertIs(verdict.action, Action.REJECT)
        self.assertEqual(verdict.reason, "UNKNOWN_PHASE")


class PolicyFileValidationTests(unittest.TestCase):
    def _valid(self) -> dict:
        with open(os.path.join(os.path.dirname(__file__), "..", "..", "config", "phase_policy.json"),
                  encoding="utf-8") as fh:
            return json.load(fh)

    def test_shipped_policy_file_matches_code_defaults(self):
        loaded = policy_from_dict(self._valid())
        for phase in PHASES:
            self.assertEqual(loaded.rule_for(phase).mode, DEFAULT_POLICY.rule_for(phase).mode)
            self.assertEqual(loaded.rule_for(phase).required, DEFAULT_POLICY.rule_for(phase).required)

    def test_file_cannot_enable_a_live_action(self):
        data = self._valid()
        data["phases"]["EARLY"]["mode"] = "LIVE"
        with self.assertRaises(ConfigurationError):
            policy_from_dict(data)

    def test_file_cannot_remove_the_safety_floor_from_entry_phases(self):
        data = self._valid()
        data["phases"]["GROWTH"]["required"] = ["liquidity"]  # drops safety, holders, ai
        with self.assertRaises(ConfigurationError):
            policy_from_dict(data)

    def test_unknown_top_level_or_rule_keys_are_rejected(self):
        for mutate in (lambda d: d.update(extra=1),
                       lambda d: d["phases"]["EARLY"].update(bypass=True)):
            data = self._valid()
            mutate(data)
            with self.subTest(), self.assertRaises(ConfigurationError):
                policy_from_dict(data)

    def test_unknown_evidence_name_is_rejected(self):
        data = self._valid()
        data["phases"]["EARLY"]["required"].append("vibes")
        with self.assertRaises(ConfigurationError):
            policy_from_dict(data)

    def test_missing_phase_is_rejected(self):
        data = self._valid()
        del data["phases"]["MATURE"]
        with self.assertRaises(ConfigurationError):
            policy_from_dict(data)

    def test_wrong_version_and_bool_version_are_rejected(self):
        for version in (2, True, "1"):
            data = self._valid()
            data["version"] = version
            with self.subTest(version=version), self.assertRaises(ConfigurationError):
                policy_from_dict(data)

    def test_load_policy_fails_closed_on_bad_json_and_missing_file(self):
        with tempfile.TemporaryDirectory() as d:
            bad = os.path.join(d, "bad.json")
            with open(bad, "w", encoding="utf-8") as fh:
                fh.write("{not json")
            with self.assertRaises(ConfigurationError):
                load_policy(bad)
            with self.assertRaises(ConfigurationError):
                load_policy(os.path.join(d, "absent.json"))

    def test_rule_post_init_enforces_floor_directly(self):
        with self.assertRaises(ConfigurationError):
            PhaseRule(Action.ENTER_PAPER, frozenset({"liquidity"}))
        with self.assertRaises(ConfigurationError):
            PhasePolicy({"UNKNOWN": PhaseRule(Action.WATCH)})  # incomplete phase set


if __name__ == "__main__":
    unittest.main()
