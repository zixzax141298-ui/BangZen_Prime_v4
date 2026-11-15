import asyncio
import logging
from types import SimpleNamespace

from bangzen_prime.core.operating_config import BotConfig
from bangzen_prime.strategies import STRATEGY_REGISTRY

logger = logging.getLogger("BANGZEN.Dispatcher")


class StrategyDispatcher:
    def __init__(self):
        self.config = BotConfig()

    async def route_and_evaluate(self, token_data: dict) -> dict:
        age = token_data.get("age_minutes", 999)
        mcap = token_data.get("mcap", token_data.get("market_cap", 0))
        change_5m = token_data.get("change_5m", 0)
        change_1h = token_data.get("change_1h", 0)
        vol_1h = token_data.get("vol_1h", 0)
        smart_money = token_data.get("smart_money", 0)

        selected_id = None
        reason = ""

        # ROUTING LOGIC
        if age < 5:
            if mcap < 10000:
                selected_id, reason = "sniper_degen", "SUPER_FRESH_MICRO_CAP"
            elif mcap < 50000:
                selected_id, reason = "sniper", "FRESH_LAUNCH"
            else:
                selected_id, reason = "sniper_conservative", "FRESH_LARGER_CAP"
        elif age < 15:
            if vol_1h > 10000:
                selected_id, reason = "volume_surge", "EARLY_VOLUME_SURGE"
            elif vol_1h > 5000:
                selected_id, reason = "volume_anomaly", "EARLY_VOLUME_ANOMALY"
            else:
                selected_id, reason = "degen_ignition", "DEGEN_WINDOW"
        elif age < 240:
            if change_1h > 100:
                selected_id, reason = "momentum", "STRONG_1H_MOMENTUM"
            elif change_5m < -30:
                selected_id, reason = "mean_reversion", "OVERSOLD_5M"
            elif change_5m < -15:
                selected_id, reason = "flush_recovery", "FLUSH_RECOVERY"
            elif change_1h > 20:
                selected_id, reason = "volatility_breakout", "BREAKOUT"
            elif token_data.get("has_narrative"):
                selected_id, reason = "narrative_tracker", "NARRATIVE_PLAY"
            else:
                selected_id, reason = "reversal", "POTENTIAL_REVERSAL"
        else:
            if token_data.get("is_graduating"):
                selected_id, reason = "graduation", "MIGRATING"
            elif smart_money > 2:
                selected_id, reason = "migration_snipe", "SMART_MONEY_FOLLOW"
            elif change_1h > 10:
                selected_id, reason = "range_rotation", "UPTREND_ROTATION"
            else:
                return {"status": "WATCH", "reason": "NO_STRATEGY_MATCHED"}

        strategy_class = STRATEGY_REGISTRY.get(selected_id)
        if not strategy_class:
            return {
                "status": "WATCH",
                "strategy": selected_id,
                "reason": "STRATEGY_NOT_AVAILABLE",
            }

        try:
            # 1. Inisialisasi
            try:
                strategy_instance = strategy_class(self.config)
            except TypeError:
                strategy_instance = strategy_class()

            # 2. Ubah dict ke Objek (untuk BANGZEN)
            market_data_obj = SimpleNamespace(**token_data)

            # 3. Eksekusi
            if getattr(strategy_instance, "uses_market_data", False):
                signal = strategy_instance.evaluate_token(
                    token_data, market_data=market_data_obj
                )
                if signal is not None:
                    return {
                        "status": "ACCEPTED",
                        "strategy": selected_id,
                        "reason": reason,
                        "signal": signal,
                    }
            else:
                try:
                    asyncio.get_running_loop()  # raises RuntimeError when no loop runs
                    is_ok = await strategy_instance.should_evaluate(token_data)
                except RuntimeError:
                    is_ok = asyncio.run(strategy_instance.should_evaluate(token_data))

                if is_ok:
                    return {
                        "status": "ACCEPTED",
                        "strategy": selected_id,
                        "reason": reason,
                    }

            return {
                "status": "WATCH",
                "strategy": selected_id,
                "reason": "STRATEGY_REJECTED_SIGNAL",
            }

        except Exception as e:
            logger.error(f"Error menjalankan strategi {selected_id}: {e}")
            return {
                "status": "REJECTED",
                "strategy": selected_id,
                "reason": f"STRATEGY_ERROR: {e!s}",
            }
