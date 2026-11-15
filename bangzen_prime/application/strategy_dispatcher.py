"""Fail-closed strategy routing for BANGZEN PRIME.

Routing never fabricates missing market values. This component only evaluates
strategies; it does not execute trades or bypass the risk/safety pipeline.
"""

from __future__ import annotations

import inspect
import logging
import math
from decimal import Decimal
from typing import Any

from bangzen_prime.application.strategies import STRATEGY_REGISTRY
from bangzen_prime.config import BotConfig

logger = logging.getLogger("BANGZEN.Dispatcher")


class StrategyDispatcher:
    def __init__(self, config: BotConfig | None = None) -> None:
        self.config = config or BotConfig()

    @staticmethod
    def _number(
        data: dict[str, Any], *keys: str
    ) -> tuple[float | None, str | None]:
        """Read a finite numeric value; bools and numeric strings are invalid."""
        for key in keys:
            if key not in data:
                continue

            value = data[key]
            if isinstance(value, bool) or not isinstance(
                value, (int, float, Decimal)
            ):
                return None, key

            try:
                number = float(value)
            except (TypeError, ValueError, OverflowError):
                return None, key

            if not math.isfinite(number):
                return None, key

            return number, None

        return None, keys[0] if keys else None

    @staticmethod
    def _watch(reason: str, **details: Any) -> dict[str, Any]:
        return {"status": "WATCH", "reason": reason, **details}

    def _route(self, data: dict[str, Any]) -> tuple[str | None, str, list[str]]:
        if not isinstance(data, dict):
            return None, "", ["token_data"]

        missing: list[str] = []

        age, error = self._number(data, "age_minutes")
        if error:
            missing.append(error)
        elif age is not None and age < 0:
            missing.append("age_minutes_invalid")

        if missing:
            return None, "", missing

        assert age is not None

        if age < 5:
            mcap, error = self._number(data, "mcap", "market_cap")
            if error:
                return None, "", [error]
            assert mcap is not None
            if mcap < 0:
                return None, "", ["mcap_invalid"]

            if mcap < 10_000:
                return "sniper_degen", "SUPER_FRESH_MICRO_CAP", []
            if mcap < 50_000:
                return "sniper", "FRESH_LAUNCH", []
            return "sniper_conservative", "FRESH_LARGER_CAP", []

        if age < 15:
            volume, error = self._number(data, "vol_1h")
            if error:
                return None, "", [error]
            assert volume is not None
            if volume < 0:
                return None, "", ["vol_1h_invalid"]

            if volume > 10_000:
                return "volume_surge", "EARLY_VOLUME_SURGE", []
            if volume > 5_000:
                return "volume_anomaly", "EARLY_VOLUME_ANOMALY", []
            return "degen_ignition", "DEGEN_WINDOW", []

        if age < 240:
            change_1h, err_1h = self._number(data, "change_1h")
            change_5m, err_5m = self._number(data, "change_5m")
            if err_1h or err_5m:
                return None, "", [
                    field for field in (err_1h, err_5m) if field is not None
                ]

            narrative = data.get("has_narrative")
            if not isinstance(narrative, bool):
                return None, "", ["has_narrative"]

            assert change_1h is not None and change_5m is not None

            if change_1h > 100:
                return "momentum", "STRONG_1H_MOMENTUM", []
            if change_5m < -30:
                return "mean_reversion", "OVERSOLD_5M", []
            if change_5m < -15:
                return "flush_recovery", "FLUSH_RECOVERY", []
            if change_1h > 20:
                return "volatility_breakout", "BREAKOUT", []
            if narrative:
                return "narrative_tracker", "NARRATIVE_PLAY", []
            return "reversal", "POTENTIAL_REVERSAL", []

        graduating = data.get("is_graduating")
        if not isinstance(graduating, bool):
            return None, "", ["is_graduating"]

        if graduating:
            return "graduation", "MIGRATING", []

        smart_money, error = self._number(data, "smart_money")
        if error:
            return None, "", [error]

        change_1h, error = self._number(data, "change_1h")
        if error:
            return None, "", [error]

        assert smart_money is not None and change_1h is not None

        if smart_money > 2:
            return "migration_snipe", "SMART_MONEY_FOLLOW", []
        if change_1h > 10:
            return "range_rotation", "UPTREND_ROTATION", []

        return None, "NO_STRATEGY_MATCHED", []

    async def route_and_evaluate(self, token_data: dict) -> dict:
        selected_id, reason, missing = self._route(token_data)

        if missing:
            return self._watch(
                "REQUIRED_MARKET_DATA_UNAVAILABLE",
                missing_fields=missing,
            )

        if selected_id is None:
            return self._watch(reason or "NO_STRATEGY_MATCHED")

        strategy_class = STRATEGY_REGISTRY.get(selected_id)
        if strategy_class is None:
            return self._watch(
                "STRATEGY_NOT_AVAILABLE",
                strategy=selected_id,
            )

        try:
            # Inspect the constructor instead of catching TypeError. A TypeError
            # raised inside a constructor must not trigger a second construction.
            parameters = inspect.signature(strategy_class).parameters
            if "config" in parameters:
                strategy = strategy_class(config=self.config)
            else:
                strategy = strategy_class()

            if getattr(strategy, "uses_market_data", False):
                # Do not manufacture a market-data object with fabricated values.
                if not isinstance(token_data, dict):
                    return self._watch(
                        "REQUIRED_MARKET_DATA_UNAVAILABLE",
                        strategy=selected_id,
                    )

                signal = strategy.evaluate_token(
                    token_data,
                    market_data=type("MarketDataView", (), token_data)(),
                )
                if inspect.isawaitable(signal):
                    signal = await signal

                if signal is not None:
                    return {
                        "status": "ACCEPTED",
                        "strategy": selected_id,
                        "reason": reason,
                        "signal": signal,
                    }
            else:
                result = await strategy.should_evaluate(token_data)
                if result:
                    return {
                        "status": "ACCEPTED",
                        "strategy": selected_id,
                        "reason": reason,
                    }

            return self._watch(
                "STRATEGY_REJECTED_SIGNAL",
                strategy=selected_id,
            )

        except Exception as exc:
            # Do not emit exception messages or tracebacks: provider and
            # strategy exceptions may contain sensitive internal details.
            logger.error(
                "Strategy evaluation failed: %s (%s)",
                selected_id,
                type(exc).__name__,
            )
            return self._watch(
                "STRATEGY_EVALUATION_ERROR",
                strategy=selected_id,
            )
