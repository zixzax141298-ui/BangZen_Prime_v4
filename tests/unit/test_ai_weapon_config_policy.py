import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOLS_PATH = ROOT / "config" / "ai_tools.json"
MATRIX_PATH = ROOT / "config" / "strategy_matrix.json"
MAP_PATH = ROOT / "config" / "ai_tool_weapon_map.json"
CATALOG_PATH = ROOT / "config" / "weapon_catalog.json"
# Owner-authorized alignment: tools whose catalog access is DENIED were removed from the AI surface.
ALLOWED = [
    "check_sybil_cluster",
    "check_honeypot",
    "check_smart_money_quality",
    "check_sequential_bundle",
    "check_pre_dump_radar",
    "score_metadata_narrative",
    "fetch_news_keywords",
    "check_cross_chain_copycat",
    "check_autopsy_dna",
]
FORBIDDEN = [
    "evaluate_pumpfun_raydium",
    "get_session_multiplier",
    "calculate_twap_plan",
    "get_dynamic_slippage",
]


class PolicyConfigTests(unittest.TestCase):
    def test_ai_tools_expose_analysis_only_allowlist(self):
        tools = json.loads(TOOLS_PATH.read_text(encoding="utf-8"))
        names = {item["function"]["name"] for item in tools}
        assert names == set(ALLOWED)
        assert not names.intersection(FORBIDDEN)

    def test_strategy_matrix_selects_at_most_one_on_demand_weapon(self):
        matrix = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
        policy = matrix["selection_policy"]
        assert policy["purpose"] == "ANALYSIS_ONLY"
        assert policy["max_selected_weapons"] == 1
        assert policy["invoke_only_when_triggered"] is True
        assert policy["empty_selection_allowed"] is True
        names = {
            item["function"]["name"]
            for item in json.loads(TOOLS_PATH.read_text(encoding="utf-8"))
        }
        for scenario in matrix["scenarios"].values():
            assert set(scenario["candidate_weapons"]).issubset(names)

    def test_financial_capabilities_are_explicitly_forbidden(self):
        matrix = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
        boundary = matrix["capability_boundary"]
        assert len(boundary["ai_manager_must_not"]) >= 6
        assert set(boundary["forbidden_tool_ids"]) == set(FORBIDDEN)

    def test_every_ai_tool_maps_to_an_on_demand_catalog_weapon(self):
        mapping = json.loads(MAP_PATH.read_text(encoding="utf-8"))["mappings"]
        names = {
            item["function"]["name"]
            for item in json.loads(TOOLS_PATH.read_text(encoding="utf-8"))
        }
        assert set(mapping) == names
        weapons = {
            w["id"]: w
            for w in json.loads(CATALOG_PATH.read_text(encoding="utf-8"))["weapons"]
        }
        for tool, weapon_id in mapping.items():
            assert weapon_id in weapons, tool
            assert (
                weapons[weapon_id]["ai_manager_access"] == "ON_DEMAND_ANALYSIS_ONLY"
            ), tool

    def test_no_strategy_scenario_routes_to_a_denied_capability(self):
        matrix = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
        mapping = json.loads(MAP_PATH.read_text(encoding="utf-8"))["mappings"]
        for name, scenario in matrix["scenarios"].items():
            assert scenario["candidate_weapons"], name
            for tool in scenario["candidate_weapons"]:
                assert tool in mapping, (name, tool)


if __name__ == "__main__":
    unittest.main()
