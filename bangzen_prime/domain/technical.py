import logging
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Any

logger = logging.getLogger(__name__)

# ============================================================
# KONSTANTA
# ============================================================
DEFAULT_RSI_PERIOD = 14
DEFAULT_ATR_PERIOD = 14
DEFAULT_EMA_PERIOD = 20
DEFAULT_MIN_CANDLES = 50

ADAPTIVE_TIME_STOP = {
    "PRE_MIGRATION": 120,
    "FRESH_MIGRATION": 180,
    "RETEST_BOUNCE": 240,
    "SURVIVAL_FLOOR": 300,
    "TREND_CONTINUATION": 360,
}


# ============================================================
# OUTPUT DATACLASS
# ============================================================
@dataclass(frozen=True)
class ExitSignalReport:
    should_exit: bool
    reasons: tuple[str, ...]


# ============================================================
# HELPER
# ============================================================
def _safe_decimal(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    try:
        if value is None:
            return default
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


# ============================================================
# INDIKATOR DASAR
# ============================================================
def calculate_rsi(closes: list[Decimal], period: int = DEFAULT_RSI_PERIOD) -> Decimal | None:
    if len(closes) < period + 1:
        return None

    gains = Decimal("0")
    losses = Decimal("0")

    for i in range(1, period + 1):
        change = closes[i] - closes[i - 1]
        if change > 0:
            gains += change
        else:
            losses += abs(change)

    avg_g = gains / Decimal(str(period))
    avg_l = losses / Decimal(str(period))

    for i in range(period + 1, len(closes)):
        change = closes[i] - closes[i - 1]
        gain = change if change > 0 else Decimal("0")
        loss = abs(change) if change < 0 else Decimal("0")

        avg_g = (avg_g * Decimal(str(period - 1)) + gain) / Decimal(str(period))
        avg_l = (avg_l * Decimal(str(period - 1)) + loss) / Decimal(str(period))

    if avg_l == 0:
        return Decimal("50.0") if avg_g == 0 else Decimal("100.0")
    if avg_g == 0:
        return Decimal("0.0")

    rs = avg_g / avg_l
    rsi = Decimal("100") - (Decimal("100") / (Decimal("1") + rs))
    return rsi.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_atr(
    highs: list[Decimal], lows: list[Decimal], closes: list[Decimal], period: int = DEFAULT_ATR_PERIOD
) -> Decimal | None:
    if len(closes) < period + 1:
        return None

    trs = []
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)

    recent_trs = trs[-period:]
    return sum(recent_trs) / Decimal(str(period))


def ema_series(values: list[Decimal], period: int) -> list[Decimal]:
    if not values:
        return []
    k = Decimal("2") / (Decimal(str(period)) + Decimal("1"))
    out = [values[0]]
    for v in values[1:]:
        out.append(v * k + out[-1] * (Decimal("1") - k))
    return out


def pivot_lows(lows: list[Decimal], k: int = 2) -> list[tuple[int, Decimal]]:
    out = []
    for i in range(k, len(lows) - k):
        if lows[i] <= min(lows[i - k : i + k + 1]):
            if out and out[-1][0] == i - 1 and out[-1][1] == lows[i]:
                continue
            out.append((i, lows[i]))
    return out


# ============================================================
# METRIK STRUKTUR
# ============================================================
def structure_metrics(
    candles: list[list[Any]], price: Decimal, min_candles: int = DEFAULT_MIN_CANDLES
) -> dict[str, Any] | None:
    """
    Menghitung metrik struktur dari candle (format: [time, open, high, low, close, volume]).
    """
    if len(candles) < min_candles:
        return None

    o = [_safe_decimal(c[1]) for c in candles]
    h = [_safe_decimal(c[2]) for c in candles]
    l = [_safe_decimal(c[3]) for c in candles]
    c_ = [_safe_decimal(c[4]) for c in candles]
    v = [_safe_decimal(c[5]) for c in candles]

    current_price = price if price > 0 else c_[-1]
    ath = max(h)
    if ath <= 0:
        return None

    ath_idx = len(h) - 1 - h[::-1].index(ath)
    pre_low = min(l[: ath_idx + 1])
    low_after = min(l[ath_idx:])

    pump_leg = (ath / pre_low - Decimal("1")) * Decimal("100") if pre_low > 0 else Decimal("0")
    dd = max(Decimal("0"), (ath - current_price) / ath * Decimal("100"))
    bounce = (current_price / low_after - Decimal("1")) * Decimal("100") if low_after > 0 else Decimal("0")

    piv = [p for p in pivot_lows(l) if p[0] >= ath_idx]
    higher_low = len(piv) >= 2 and piv[-1][1] >= piv[-2][1] * Decimal("1.01")
    base_low = piv[-1][1] if piv else low_after

    ema = ema_series(c_, DEFAULT_EMA_PERIOD)
    ema20 = ema[-1]
    ema_slope = (ema[-1] / ema[-4] - Decimal("1")) * Decimal("100") if len(ema) >= 4 and ema[-4] > 0 else Decimal("0")
    price_vs_ema = (current_price / ema20 - Decimal("1")) * Decimal("100") if ema20 > 0 else Decimal("0")

    recent_v = (v[-3] + v[-2]) / Decimal("2") if len(v) >= 3 else Decimal("0")
    base_list = v[-15:-3] if len(v) >= 15 else v[:-3]
    base_v = sum(base_list) / Decimal(str(len(base_list))) if base_list else Decimal("0")
    vol_ratio = recent_v / base_v if base_v > 0 else Decimal("1.0")

    drops = [(c_[i] - o[i]) / o[i] * Decimal("100") for i in range(-6, 0) if o[i] > 0]
    atr = calculate_atr(h, l, c_)

    streak = 0
    for i in range(len(c_) - 1, -1, -1):
        if c_[i] > o[i]:
            streak += 1
        else:
            break

    wicks = [(h[i] - max(o[i], c_[i])) / (h[i] - l[i]) for i in range(-3, 0) if h[i] > l[i]]
    upper_wick_avg = sum(wicks) / Decimal(str(len(wicks))) if wicks else Decimal("0")

    near_high = current_price >= max(h[-12:]) * Decimal("0.97")
    roll = [sum(v[i : i + 3]) / Decimal("3") for i in range(len(v) - 2)]
    peak_roll = max(roll) if roll else Decimal("0")

    return {
        "candles": len(candles),
        "ath": ath,
        "dd": dd.quantize(Decimal("0.1")),
        "bounce": bounce.quantize(Decimal("0.1")),
        "pump_leg": pump_leg.quantize(Decimal("0.1")),
        "candles_since_ath": len(candles) - ath_idx - 1,
        "higher_low": higher_low,
        "base_low": base_low,
        "fresh_low": min(l[-8:]),
        "ema20": ema20,
        "ema_slope": ema_slope.quantize(Decimal("0.01")),
        "price_vs_ema": price_vs_ema.quantize(Decimal("0.1")),
        "vol_ratio": vol_ratio.quantize(Decimal("0.01")),
        "max_drop_6": (min(drops) if drops else Decimal("0.0")).quantize(Decimal("0.1")),
        "rsi": calculate_rsi(c_, DEFAULT_RSI_PERIOD),
        "atr_pct": (atr / current_price * Decimal("100")).quantize(Decimal("0.01")) if atr and current_price > 0 else None,
        "green_streak": streak,
        "upper_wick_avg": upper_wick_avg.quantize(Decimal("0.01")),
        "vol_divergence": bool(near_high and vol_ratio < Decimal("0.8")),
        "ext_atr": ((current_price - ema20) / atr).quantize(Decimal("0.01")) if atr and atr > 0 else Decimal("0"),
        "vol_retention": (recent_v / peak_roll).quantize(Decimal("0.01")) if peak_roll > 0 else Decimal("1.0"),
    }


# ============================================================
# ADAPTIVE TIME STOP
# ============================================================
def adaptive_time_stop_min(setup: str) -> int:
    """Mengembalikan durasi time-stop dalam menit berdasarkan setup."""
    return ADAPTIVE_TIME_STOP.get(setup, 180)


# ============================================================
# EXIT SIGNALS (Evaluasi Exit)
# ============================================================
def evaluate_exit_signals(
    row: dict[str, Any] | None,
    candles: list[list[Any]],
    market: dict[str, Any],
) -> ExitSignalReport:
    """
    Mengevaluasi apakah posisi harus keluar berdasarkan:
    - Lower-high di bawah EMA20
    - Volume drop > 50%
    - Seller dominan + break swing low
    """
    if not candles or len(candles) < 4:
        return ExitSignalReport(False, ("insufficient_candles",))

    c_list = candles[-5:]
    closes = [_safe_decimal(c[3]) for c in c_list]
    highs = [_safe_decimal(c[1]) for c in c_list]
    lows = [_safe_decimal(c[2]) for c in c_list]
    vols = [_safe_decimal(c[4]) for c in c_list]

    ema = ema_series([_safe_decimal(c[3]) for c in candles], DEFAULT_EMA_PERIOD)
    ema20 = ema[-1] if ema else Decimal("0")

    lh_ema = (
        len(closes) >= 2
        and highs[-1] < highs[-2]
        and closes[-1] < ema20
        and closes[-2] < ema20
    )

    v_peak = (
        max([_safe_decimal(c[4]) for c in candles[-15:]])
        if len(candles) >= 15
        else (max(vols) if vols else Decimal("0"))
    )
    v_fading = vols[-1] <= v_peak * Decimal("0.50") if v_peak > 0 else False

    m = market or {}
    bs_m5 = _safe_decimal(m.get("buy_ratio_m5"))
    txns_m5 = _safe_int(m.get("txns_m5"))
    seller_dom = bs_m5 < Decimal("0.45") and txns_m5 >= 10

    piv = pivot_lows([_safe_decimal(c[2]) for c in candles])
    swing_low = piv[-1][1] if piv else (lows[-2] if len(lows) >= 2 else Decimal("0"))
    break_low = lows[-1] < swing_low * Decimal("0.99") if swing_low > 0 else False

    reasons = []
    if lh_ema:
        reasons.append("lower_high_below_ema20")
    if v_fading:
        reasons.append("volume_drop_50%")
    if seller_dom:
        reasons.append("seller_dominant_m5")
    if break_low:
        reasons.append("structure_swing_low_break")

    should_exit = (lh_ema and v_fading) or (seller_dom and break_low)
    return ExitSignalReport(should_exit, tuple(reasons) if should_exit else ())
