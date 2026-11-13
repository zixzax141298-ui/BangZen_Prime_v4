import logging
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PumpfunParams:
    early_min_age_min: Decimal = Decimal("0.5")
    early_max_age_min: Decimal = Decimal("10.0")
    early_min_mcap: Decimal = Decimal("5000")
    early_max_mcap: Decimal = Decimal("50000")
    early_min_holders: int = 30
    early_max_holders: int = 500
    early_max_top10: Decimal = Decimal("35.0")
    early_max_dev: Decimal = Decimal("5.0")
    early_max_bundle: Decimal = Decimal("20.0")
    early_min_unique_buyers_5m: int = 10
    early_min_buy_sell_ratio_5m: Decimal = Decimal("1.2")
    final_min_curve: Decimal = Decimal("85.0")
    final_max_curve: Decimal = Decimal("99.0")
    final_min_age_min: Decimal = Decimal("5.0")
    final_max_age_min: Decimal = Decimal("60.0")
    final_min_holders: int = 100
    final_max_top10: Decimal = Decimal("25.0")
    final_max_dev: Decimal = Decimal("3.0")
    final_max_bundle: Decimal = Decimal("10.0")
    final_min_unique_buyers_10m: int = 30
    final_min_buy_sell_ratio_5m: Decimal = Decimal("1.5")
    final_max_early_holder_retention: Decimal = Decimal("20.0")
    hold_min_smart_money: int = 2
    hold_trail_pct: Decimal = Decimal("22.0")
    hold_hard_tp_pct: Decimal = Decimal("250.0")
    hold_time_stop_min: int = 45
    scalp_tp_pct: Decimal = Decimal("45.0")
    scalp_sl_pct: Decimal = Decimal("19.0")
    scalp_time_stop_min: int = 14


@dataclass(frozen=True)
class RealisticTradePlan:
    setup: str
    mode: str
    tp1_pct: Decimal | None = None
    sl_pct: Decimal | None = None
    trailing_pct: Decimal | None = None
    hard_tp_pct: Decimal | None = None
    time_stop_min: int | None = None
    has_quality_smart_money: bool = False


@dataclass(frozen=True)
class RealisticPumpfunReport:
    status: str
    reason: str
    plan: RealisticTradePlan | None = None


class RealisticPumpfunEngine:
    def __init__(self, params: PumpfunParams | None = None):
        self.p = params or PumpfunParams()

    def _safe_decimal(self, value: Any, default: Decimal = Decimal("0")) -> Decimal:
        try:
            if value is None:
                return default
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            return default

    def _safe_int(self, value: Any, default: int = 0) -> int:
        try:
            if value is None:
                return default
            return int(float(value))
        except (TypeError, ValueError):
            return default

    def _get_bs_m5(self, m: dict) -> Decimal:
        v = self._safe_decimal(m.get("bs_ratio_m5"))
        if v > 0:
            return v
        v_bs = self._safe_decimal(m.get("buy_sell_ratio_m5"))
        if v_bs > 0:
            return v_bs
        share = self._safe_decimal(m.get("buy_ratio_m5"))
        if share >= 1:
            return Decimal("5.0")
        if share <= 0:
            return Decimal("0")
        return min(share / (Decimal("1.0") - share), Decimal("5.0"))

    def _detect_early(self, m: dict, a: dict) -> bool:
        if m.get("dex") != "pumpfun":
            return False
        age = self._safe_decimal(m.get("age_min"))
        if not (self.p.early_min_age_min <= age <= self.p.early_max_age_min):
            return False
        mc = self._safe_decimal(m.get("mc"))
        if not (self.p.early_min_mcap <= mc <= self.p.early_max_mcap):
            return False
        holders = self._safe_int(a.get("holder_count"))
        if not (self.p.early_min_holders <= holders <= self.p.early_max_holders):
            return False
        if self._safe_decimal(a.get("top10_pct")) > self.p.early_max_top10:
            return False
        if self._safe_decimal(a.get("dev_pct")) > self.p.early_max_dev:
            return False
        bundle = self._safe_decimal(a.get("bundler_total_pct")) + self._safe_decimal(a.get("snipers_pct"))
        if bundle > self.p.early_max_bundle:
            return False
        unique_5m = self._safe_int(m.get("buyers_m5") or m.get("unique_buyers_m5"))
        if unique_5m < self.p.early_min_unique_buyers_5m:
            return False
        if self._get_bs_m5(m) < self.p.early_min_buy_sell_ratio_5m:
            return False
        return True

    def _detect_final(self, m: dict, a: dict) -> bool:
        if m.get("dex") != "pumpfun":
            return False
        curve = self._safe_decimal(a.get("curve_pct"))
        if not (self.p.final_min_curve <= curve <= self.p.final_max_curve):
            return False
        age = self._safe_decimal(m.get("age_min"))
        if not (self.p.final_min_age_min <= age <= self.p.final_max_age_min):
            return False
        holders = self._safe_int(a.get("holder_count"))
        if holders < self.p.final_min_holders:
            return False
        if self._safe_decimal(a.get("top10_pct")) > self.p.final_max_top10:
            return False
        if self._safe_decimal(a.get("dev_pct")) > self.p.final_max_dev:
            return False
        bundle = self._safe_decimal(a.get("bundler_total_pct")) + self._safe_decimal(a.get("snipers_pct"))
        if bundle > self.p.final_max_bundle:
            return False
        unique_10m = self._safe_int(m.get("buyers_m10") or m.get("unique_buyers_m10") or m.get("buyers_m5"))
        if unique_10m < self.p.final_min_unique_buyers_10m:
            return False
        if self._get_bs_m5(m) < self.p.final_min_buy_sell_ratio_5m:
            return False
        early_ret = self._safe_decimal(a.get("early_holder_retention_pct") or a.get("top_early_pct"))
        if early_ret > self.p.final_max_early_holder_retention:
            return False
        return True

    def _build_plan(self, setup: str, a: dict) -> RealisticTradePlan:
        sm_count = self._safe_int(a.get("smart_money_count"))
        has_quality_sm = sm_count >= self.p.hold_min_smart_money
        if has_quality_sm:
            return RealisticTradePlan(
                setup=setup, mode="HOLD",
                trailing_pct=self.p.hold_trail_pct,
                hard_tp_pct=self.p.hold_hard_tp_pct,
                time_stop_min=self.p.hold_time_stop_min,
                has_quality_smart_money=True,
            )
        return RealisticTradePlan(
            setup=setup, mode="SCALP",
            tp1_pct=self.p.scalp_tp_pct,
            sl_pct=self.p.scalp_sl_pct,
            time_stop_min=self.p.scalp_time_stop_min,
            has_quality_smart_money=False,
        )

    def evaluate(self, m: dict, a: dict) -> RealisticPumpfunReport:
        if self._detect_early(m, a):
            plan = self._build_plan("PUMPFUN_EARLY", a)
            return RealisticPumpfunReport(status="PUMPFUN_EARLY", reason="all_filters_passed", plan=plan)
        if self._detect_final(m, a):
            plan = self._build_plan("PUMPFUN_FINAL", a)
            return RealisticPumpfunReport(status="PUMPFUN_FINAL", reason="all_filters_passed", plan=plan)
        return RealisticPumpfunReport(status="NONE", reason="no_match")
