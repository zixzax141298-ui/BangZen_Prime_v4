import logging
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

logger = logging.getLogger(__name__)

# ============================================================
# Dataclass untuk Output yang bersih (Pilar No. 2)
# ============================================================
@dataclass(frozen=True)
class BlackOpsReport:
    flags: tuple[str, ...]
    metrics: dict[str, Any]
    edge: str
    holy_grail_score: Decimal
    whale_accumulation: bool
    graduation_action: str

class BlackOpsEngine:
    """
    Absolute Edge Engine (v3).
    Mendeteksi Slow Rug, KOL Bait, Gradual Dump, dan Whale Accumulation.
    """

    def __init__(self):
        pass

    def _safe_decimal(self, value: Any) -> Decimal:
        try:
            if value is None:
                return Decimal("0")
            return Decimal(str(value))
        except Exception:
            return Decimal("0")

    def _safe_int(self, value: Any) -> int:
        try:
            if value is None:
                return 0
            return int(float(value))
        except Exception:
            return 0

    def _bs_m5(self, m: dict) -> Decimal:
        if not isinstance(m, dict):
            return Decimal("1.0")
        
        v = self._safe_decimal(m.get("bs_ratio_m5"))
        if v > 0:
            return v
            
        v_bs = self._safe_decimal(m.get("buy_sell_ratio_m5"))
        if v_bs > 0:
            return v_bs
            
        b5 = self._safe_decimal(m.get("b5") or m.get("buys_m5") or m.get("buys_5m"))
        s5 = self._safe_decimal(m.get("s5") or m.get("sells_m5") or m.get("sells_5m"))
        
        if b5 > 0 or s5 > 0:
            if s5 <= 0:
                return Decimal("5.0")
            return min(b5 / s5, Decimal("5.0"))
            
        share = self._safe_decimal(m.get("buy_ratio_m5"))
        if share >= Decimal("1.0"):
            return Decimal("5.0")
        if share <= Decimal("0"):
            return Decimal("0")
            
        return min(share / (Decimal("1.0") - share), Decimal("5.0"))

    def _is_slow_rug(self, m: dict, a: dict, s: dict) -> tuple[bool, str]:
        if not s.get("snapshot_ready"):
            return False, "no_snapshot_yet"

        unique_now = self._safe_int(m.get("buyers_m5") or m.get("unique_buyers_m5") or m.get("buyers_5m"))
        unique_prev = self._safe_int(s.get("unique_m5_prev"))
        buy_ratio = self._bs_m5(m)
        holders_now = self._safe_int(a.get("holder_count") or a.get("holders"))
        holders_prev = self._safe_int(s.get("holders_prev") or holders_now)

        unique_stagnant = Decimal(str(unique_now)) <= max(Decimal(str(unique_prev)) * Decimal("1.08"), Decimal(str(unique_prev + 2)))
        buy_ratio_weak = Decimal("0") < buy_ratio < Decimal("1.35")
        holder_stagnant = holders_now <= holders_prev + 4

        if unique_stagnant and buy_ratio_weak and holder_stagnant:
            reason = f"slow_rug: unique {unique_prev}->{unique_now}, buy_ratio={buy_ratio:.2f}, holders {holders_prev}->{holders_now}"
            return True, reason
        return False, ""

    def _is_kol_bait(self, m: dict, s: dict) -> tuple[bool, str]:
        if not s.get("snapshot_ready"):
            return False, "no_snapshot_yet"

        vol_now = self._safe_decimal(m.get("vol5m") or m.get("volume_m5") or m.get("vol_m5"))
        vol_prev = self._safe_decimal(s.get("vol5m_prev") or "1.0")
        unique_now = self._safe_int(m.get("buyers_m5") or m.get("unique_buyers_m5") or m.get("buyers_5m"))
        unique_prev = self._safe_int(s.get("unique_m5_prev") or 1)

        if vol_prev <= 0: vol_prev = Decimal("1.0")
        if unique_prev <= 0: unique_prev = 1

        vol_spike = vol_now > vol_prev * Decimal("2.7")
        unique_flat = Decimal(str(unique_now)) < Decimal(str(unique_prev)) * Decimal("1.22")

        if vol_spike and unique_flat:
            return True, f"kol_bait: vol {vol_prev:.1f}->{vol_now:.1f}, unique {unique_prev}->{unique_now}"
        return False, ""

    def _is_gradual_dump(self, m: dict, s: dict) -> tuple[bool, str]:
        if not s.get("snapshot_ready"):
            return False, "no_snapshot_yet"

        price_now = self._safe_decimal(m.get("price") or m.get("price_usd") or m.get("priceUsd"))
        price_prev = self._safe_decimal(s.get("price_prev") or price_now)

        p5m = self._safe_decimal(m.get("price_change_m5") or m.get("pc_5m") or m.get("change_5m"))
        p15m = self._safe_decimal(m.get("price_change_m15") or m.get("pc_15m") or m.get("change_15m"))

        buy_ratio = self._bs_m5(m)
        buy_ratio_prev = self._safe_decimal(s.get("buy_ratio_prev") or buy_ratio)

        unique_now = self._safe_int(m.get("buyers_m5") or m.get("unique_buyers_m5") or m.get("buyers_5m"))
        unique_prev = self._safe_int(s.get("unique_m5_prev") or unique_now)

        vol_now = self._safe_decimal(m.get("vol5m") or m.get("volume_m5") or m.get("vol_m5"))
        vol_prev = self._safe_decimal(s.get("vol5m_prev") or vol_now or "1.0")

        price_down_slow = False
        if p5m != 0:
            price_down_slow = Decimal("-18.0") <= p5m <= Decimal("-4.0")
        elif price_prev > 0:
            change_pct = ((price_now - price_prev) / price_prev) * Decimal("100")
            price_down_slow = Decimal("-18.0") <= change_pct <= Decimal("-4.0")

        sell_pressure_up = Decimal("0") < buy_ratio < buy_ratio_prev and buy_ratio < Decimal("1.25")
        unique_weak = Decimal(str(unique_now)) <= Decimal(str(unique_prev)) * Decimal("1.05")
        vol_not_spike = vol_now < vol_prev * Decimal("2.2")

        confirm_15m = True
        if p15m != 0:
            confirm_15m = p15m < Decimal("-6.0")

        is_dump = price_down_slow and sell_pressure_up and unique_weak and vol_not_spike and confirm_15m

        if is_dump:
            return True, f"gradual_dump: p5m={p5m:.1f}%, buy_ratio {buy_ratio_prev:.2f}->{buy_ratio:.2f}, unique {unique_prev}->{unique_now}"
        return False, ""

    def _graduation_action(self, a: dict, m: dict, s: dict) -> tuple[str, str]:
        curve = self._safe_decimal(a.get("curve_pct") or a.get("bonding_curve_pct"))
        if curve < Decimal("88.0"):
            return "HOLD", f"curve={curve:.1f}% still early"

        early_ret = self._safe_decimal(a.get("early_holder_retention_pct") or a.get("top_early_pct") or a.get("early_pct"))
        top10 = self._safe_decimal(a.get("top10_pct") or a.get("top10"))
        unique_now = self._safe_int(m.get("buyers_m5") or m.get("unique_buyers_m5") or m.get("buyers_5m"))
        unique_prev = self._safe_int(s.get("unique_m5_prev") or 0)

        unique_accel = Decimal(str(unique_now)) > Decimal(str(unique_prev)) * Decimal("1.40") and unique_now >= 40

        if early_ret > Decimal("30.0") or top10 > Decimal("38.0"):
            return "EXIT", f"graduation_dump_risk: early_ret={early_ret:.1f}%, top10={top10:.1f}%"

        if unique_accel and top10 < Decimal("23.0") and early_ret < Decimal("17.0"):
            return "BUY_DIP", f"buy_dip_ok: unique_accel + low concentration (top10={top10:.1f}%)"

        if Decimal("90.0") <= curve <= Decimal("95.0"):
            return "WATCH", f"curve={curve:.1f}%, watching graduation zone"

        return "HOLD", f"curve={curve:.1f}%, waiting"

    def _unique_buyer_velocity(self, m: dict, s: dict) -> Decimal:
        unique_now = self._safe_int(m.get("buyers_m5") or m.get("unique_buyers_m5") or m.get("buyers_5m"))
        unique_prev = self._safe_int(s.get("unique_m5_prev") or 0)
        delta = max(unique_now - unique_prev, 0)
        return (Decimal(str(delta)) / Decimal("5.0")).quantize(Decimal("0.01"))

    def _holy_grail_score(self, m: dict, a: dict, s: dict) -> tuple[Decimal, str]:
        velocity = self._unique_buyer_velocity(m, s)
        top10 = self._safe_decimal(a.get("top10_pct") or a.get("top10"))
        buy_ratio = self._bs_m5(m)
        holders = self._safe_int(a.get("holder_count") or a.get("holders"))
        smart_money = self._safe_int(a.get("smart_money_count") or a.get("sm_count") or a.get("whale_count"))

        vel_score = min(velocity * Decimal("12.0"), Decimal("40.0"))
        conc_score = max(Decimal("0"), Decimal("30.0") - max(top10 - Decimal("15.0"), Decimal("0")) * Decimal("1.5"))
        ratio_score = min(max(buy_ratio - Decimal("1.0"), Decimal("0")) * Decimal("20.0"), Decimal("20.0"))
        holder_bonus = Decimal("10.0") if holders >= 80 else (Decimal("5.0") if holders >= 50 else Decimal("0"))
        sm_bonus = Decimal("8.0") if smart_money >= 2 else (Decimal("4.0") if smart_money >= 1 else Decimal("0"))

        score = min(vel_score + conc_score + ratio_score + holder_bonus + sm_bonus, Decimal("100.0"))
        score = score.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)

        breakdown = f"vel={velocity:.1f}({vel_score:.0f}) conc={top10:.1f}%({conc_score:.0f}) ratio={buy_ratio:.2f}({ratio_score:.0f}) holders={holders} sm={smart_money}"
        return score, breakdown

    def _is_whale_accumulation(self, m: dict, a: dict, s: dict) -> tuple[bool, str]:
        smart_money = self._safe_int(a.get("smart_money_count") or a.get("sm_count") or a.get("whale_count"))
        smart_money_prev = self._safe_int(s.get("smart_money_prev") or 0)

        large_buys = self._safe_int(m.get("large_buys_m5") or m.get("whale_buys_m5") or m.get("buys_above_1sol_m5") or a.get("large_buy_count"))
        large_buys_prev = self._safe_int(s.get("large_buys_prev") or 0)

        buy_ratio = self._bs_m5(m)
        unique_now = self._safe_int(m.get("buyers_m5") or m.get("unique_buyers_m5") or m.get("buyers_5m"))
        unique_prev = self._safe_int(s.get("unique_m5_prev") or unique_now)

        top10 = self._safe_decimal(a.get("top10_pct") or a.get("top10"))
        vol_now = self._safe_decimal(m.get("vol5m") or m.get("volume_m5") or m.get("vol_m5"))
        vol_prev = self._safe_decimal(s.get("vol5m_prev") or vol_now or "1.0")

        sm_growing = smart_money >= 2 and (smart_money > smart_money_prev or smart_money >= 3)
        large_buy_up = large_buys >= 2 and large_buys >= large_buys_prev
        strong_buy = buy_ratio >= Decimal("1.55")
        unique_healthy = Decimal(str(unique_now)) >= max(Decimal(str(unique_prev)) * Decimal("0.9"), Decimal("15"))
        concentration_ok = top10 <= Decimal("32.0")
        vol_reasonable = vol_now < vol_prev * Decimal("3.5") if vol_prev > 0 else True

        is_acc = (sm_growing or large_buy_up) and strong_buy and unique_healthy and concentration_ok and vol_reasonable

        if is_acc:
            return True, f"whale_acc: sm={smart_money} (prev={smart_money_prev}), large_buys={large_buys}, buy_ratio={buy_ratio:.2f}, unique={unique_now}, top10={top10:.1f}%"
        return False, ""

    def analyze(self, m: dict, a: dict, s: dict) -> BlackOpsReport:
        """Fungsi utama untuk memproses semua senjata Black Ops."""
        flags: list[str] = []
        metrics: dict[str, Any] = {
            "graduation_action": "HOLD",
            "unique_velocity": Decimal("0"),
            "holy_grail_score": Decimal("0"),
            "whale_accumulation": False,
            "edge": "unknown",
            "reasons": [],
            "warnings": [],
            "score_breakdown": "",
        }

        red_flags: list[str] = []
        
        is_rug, rug_reason = self._is_slow_rug(m, a, s)
        if is_rug:
            red_flags.append("slow_rug")
            metrics["reasons"].append(rug_reason)

        is_bait, bait_reason = self._is_kol_bait(m, s)
        if is_bait:
            red_flags.append("kol_bait")
            metrics["reasons"].append(bait_reason)

        is_gdump, gdump_reason = self._is_gradual_dump(m, s)
        if is_gdump:
            red_flags.append("gradual_dump")
            metrics["reasons"].append(gdump_reason)

        if len(red_flags) >= 2:
            flags.extend(red_flags)
        elif len(red_flags) == 1:
            metrics["warnings"] = red_flags

        action, action_reason = self._graduation_action(a, m, s)
        metrics["graduation_action"] = action
        metrics["reasons"].append(action_reason)
        if action == "EXIT":
            flags.append("graduation_dump_risk")

        velocity = self._unique_buyer_velocity(m, s)
        score, breakdown = self._holy_grail_score(m, a, s)
        metrics["unique_velocity"] = velocity
        metrics["holy_grail_score"] = score
        metrics["score_breakdown"] = breakdown

        is_whale, whale_reason = self._is_whale_accumulation(m, a, s)
        metrics["whale_accumulation"] = is_whale
        if is_whale:
            metrics["reasons"].append(whale_reason)

        if is_whale and not flags and score >= Decimal("60"):
            metrics["edge"] = "whale_driven"
        elif not flags and score >= Decimal("72"):
            metrics["edge"] = "strong_organic"
        elif not flags and score >= Decimal("55"):
            metrics["edge"] = "acceptable"
        elif "slow_rug" in flags or "kol_bait" in flags or "gradual_dump" in flags:
            metrics["edge"] = "toxic"
        else:
            metrics["edge"] = "weak"

        return BlackOpsReport(
            flags=tuple(flags),
            metrics=metrics,
            edge=metrics["edge"],
            holy_grail_score=score,
            whale_accumulation=is_whale,
            graduation_action=action
        )
