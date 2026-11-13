import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "config" / "weapon_catalog.json"


class PolicyConfigTests(unittest.TestCase):
    def test_weapon_inventory_matches_owner_declared_count_and_categories(self):
        data = json.loads(CATALOG.read_text(encoding="utf-8"))
        assert data["declared_count"] == 29
        assert len(data["weapons"]) == 29
        assert data["category_counts"] == {"MARKET_READING": 8, "RISK_MANAGEMENT": 10, "EXECUTION": 6, "CORE_STRATEGY": 5}
        assert len({item["id"] for item in data["weapons"]}) == 29

    def test_ai_manager_never_receives_execution_or_core_strategy_authority(self):
        data = json.loads(CATALOG.read_text(encoding="utf-8"))
        for weapon in data["weapons"]:
            if weapon["category"] in {"EXECUTION", "CORE_STRATEGY"}:
                assert weapon["ai_manager_access"] == "DENIED"

    def test_ai_manager_is_on_demand_and_cannot_make_financial_decisions(self):
        policy = json.loads(CATALOG.read_text(encoding="utf-8"))["ai_manager_policy"]
        assert policy["max_selected_weapons"] == 1
        assert policy["may_select_zero"] is True
        assert policy["may_not_manage_finances_or_balances"] is True
        assert policy["may_not_create_buy_sell_or_tp_sl_plans"] is True
        assert policy["may_not_authorize_or_execute_transactions"] is True
        assert policy["risk_safety_final_veto"] is True


if __name__ == "__main__":
    unittest.main()
