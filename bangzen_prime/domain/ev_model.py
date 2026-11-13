"""Expected-value and net risk/reward calculations using validated Decimal inputs."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from bangzen_prime.domain.values import non_negative, percent, positive
from bangzen_prime.errors import DomainError


@dataclass(frozen=True)
class TradePlanValidation:
    is_valid: bool
    reason: str
    net_rr: Decimal
    expected_value: Decimal


def _ev_inputs(
    sl_pct: Any,
    cost_pct: Any,
    tp1_pct: Any,
    tp1_sell_pct: Any,
    tp2_pct: Any,
    breakeven_buffer: Any,
) -> tuple[Decimal, Decimal, Decimal, Decimal, Decimal, Decimal]:
    stop = positive(sl_pct, "sl_pct")
    costs = non_negative(cost_pct, "cost_pct")
    first_target = positive(tp1_pct, "tp1_pct")
    first_sell = percent(tp1_sell_pct, "tp1_sell_pct")
    second_target = positive(tp2_pct, "tp2_pct")
    buffer = non_negative(breakeven_buffer, "breakeven_buffer")
    if second_target <= first_target:
        raise DomainError("tp2_pct must be greater than tp1_pct")
    if buffer > first_target:
        raise DomainError("breakeven_buffer must not exceed tp1_pct")
    return stop, costs, first_target, first_sell, second_target, buffer


def calculate_ev_model(
    sl_pct: Decimal,
    cost_pct: Decimal,
    tp1_pct: Decimal = Decimal("45.0"),
    tp1_sell_pct: Decimal = Decimal("60.0"),
    tp2_pct: Decimal = Decimal("300.0"),
    breakeven_buffer: Decimal = Decimal("5.0"),
) -> dict[str, Decimal]:
    """Calculate a scenario EV; outputs are model assumptions, not win probabilities."""
    stop, costs, first_target, first_sell_pct, second_target, buffer = _ev_inputs(
        sl_pct, cost_pct, tp1_pct, tp1_sell_pct, tp2_pct, breakeven_buffer
    )
    s1 = first_sell_pct / Decimal("100")
    g_sl = -stop
    g_be = (s1 * first_target) + ((Decimal("1") - s1) * buffer)
    g_tp2 = (s1 * first_target) + ((Decimal("1") - s1) * second_target)

    denom1 = stop + first_target
    p1_rand = stop / denom1

    d = first_target - buffer
    u = second_target - first_target
    denom2 = d + u
    q_rand = d / denom2

    w = ((Decimal("1") - q_rand) * g_be) + (q_rand * g_tp2)

    denom3 = w + stop
    p1_be = (stop + costs) / denom3 if denom3 > 0 else Decimal("1")
    p1_be = min(p1_be, Decimal("1"))

    ev_random_net = ((Decimal("1") - p1_rand) * g_sl) + (p1_rand * w) - costs

    return {
        "p1_random": round(p1_rand, 4),
        "q_random": round(q_rand, 4),
        "p1_breakeven": round(p1_be, 4),
        "ev_random_net": round(ev_random_net, 2),
    }


def validate_trade_plan(
    entry: Decimal,
    sl: Decimal,
    tp: Decimal,
    cost_pct: Decimal,
    min_net_rr: Decimal = Decimal("1.5"),
) -> TradePlanValidation:
    entry_value = positive(entry, "entry")
    stop_value = positive(sl, "sl")
    target_value = positive(tp, "tp")
    costs = non_negative(cost_pct, "cost_pct")
    minimum_rr = positive(min_net_rr, "min_net_rr")
    if not stop_value < entry_value < target_value:
        return TradePlanValidation(False, "INVALID_LEVELS", Decimal("0"), Decimal("0"))

    sl_pct = ((entry_value - stop_value) / entry_value) * Decimal("100")
    tp_pct = ((target_value - entry_value) / entry_value) * Decimal("100")

    net_profit = tp_pct - costs
    net_loss = sl_pct + costs
    if net_profit <= 0:
        return TradePlanValidation(False, "NON_POSITIVE_NET_PROFIT", Decimal("0"), Decimal("0"))
    if net_loss <= 0:
        return TradePlanValidation(False, "INVALID_LOSS", Decimal("0"), Decimal("0"))

    net_rr = net_profit / net_loss
    if net_rr < minimum_rr:
        return TradePlanValidation(False, f"NET_RR_TOO_LOW_{net_rr:.2f}", net_rr, Decimal("0"))

    ev_data = calculate_ev_model(sl_pct, costs, tp1_pct=tp_pct)
    ev_net = ev_data["ev_random_net"]

    if ev_net <= 0:
        return TradePlanValidation(False, f"NEGATIVE_EV_{ev_net:.2f}", net_rr, ev_net)

    return TradePlanValidation(True, "OK", net_rr, ev_net)
