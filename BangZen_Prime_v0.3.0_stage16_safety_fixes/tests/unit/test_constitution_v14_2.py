"""Governance guards for constitution v14.2: AI is research-only.

These tests fail if AI regains authority in the entry path: as a scan gate, as required
phase evidence, as a paper-trade veto, or as a source of BUY authorization.
"""

from __future__ import annotations

import inspect
import json
import unittest
from pathlib import Path

from bangzen_prime.core import phase_policy, use_cases
from bangzen_prime.core.errors import ConfigurationError
from bangzen_prime.core.phase_policy import Evidence, policy_from_dict
from bangzen_prime.core.use_cases import ScanMarketUseCase
from bangzen_prime.execution import paper_trading
from bangzen_prime.execution.paper_trading import PaperTradingUseCase

ROOT = Path(__file__).resolve().parents[2]


class AIHasNoEntryAuthorityTest(unittest.TestCase):
    def test_scan_use_case_does_not_accept_an_ai_brain(self):
        params = inspect.signature(ScanMarketUseCase.__init__).parameters
        for forbidden in ("ai_brain", "ai_mode", "market_sentiment"):
            self.assertNotIn(forbidden, params)

    def test_paper_engine_does_not_accept_an_ai_gate(self):
        self.assertNotIn("ai_gate", inspect.signature(PaperTradingUseCase.__init__).parameters)

    def test_evidence_has_no_ai_field(self):
        self.assertNotIn("ai", {f for f in Evidence.__dataclass_fields__})

    def test_safety_floor_does_not_require_ai(self):
        self.assertNotIn("ai", phase_policy.SAFETY_FLOOR)
        self.assertNotIn("ai", phase_policy.EVIDENCE)

    def test_source_has_no_ai_decision_authority_in_entry_path(self):
        forbidden = ('decision == "BUY"', "ai_decision", "AIBrain", "ai_gate")
        for module in (use_cases, paper_trading, phase_policy):
            source = Path(inspect.getfile(module)).read_text(encoding="utf-8")
            for token in forbidden:
                with self.subTest(module=module.__name__, token=token):
                    self.assertNotIn(token, source)


class PolicyFileMigrationTest(unittest.TestCase):
    def test_shipped_policy_file_has_no_ai_requirement(self):
        data = json.loads((ROOT / "configs" / "phase_policy.json").read_text(encoding="utf-8"))
        for name, rule in data["phases"].items():
            with self.subTest(phase=name):
                self.assertNotIn("ai", rule["required"])

    def test_old_policy_file_requiring_ai_is_refused(self):
        data = json.loads((ROOT / "configs" / "phase_policy.json").read_text(encoding="utf-8"))
        data["phases"]["EARLY"]["required"].append("ai")
        with self.assertRaises(ConfigurationError):
            policy_from_dict(data)


if __name__ == "__main__":
    unittest.main()
