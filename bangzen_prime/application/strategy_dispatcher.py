import logging
from bangzen_prime.application.strategies import STRATEGY_REGISTRY

logger = logging.getLogger("BANGZEN.Dispatcher")

class StrategyDispatcher:
    def select_and_evaluate(self, token_data: dict) -> dict:
        age_minutes = token_data.get("age_minutes", 999)
        mcap = token_data.get("market_cap_usd", 0)
        volume_1h = token_data.get("volume_1h_usd", 0)
        change_5m = token_data.get("price_change_5m_pct", 0)
        change_1h = token_data.get("price_change_1h_pct", 0)
        
        selected_id = None
        reason = ""

        if age_minutes < 5:
            selected_id = "sniper" if mcap < 20000 else "sniper_degen"
            reason = "VERY_FRESH_LAUNCH"
        elif age_minutes < 15 and volume_1h > 10000:
            selected_id = "volume_surge"
            reason = "EARLY_VOLUME_SPIKE"
        elif age_minutes < 60 and change_1h > 50:
            selected_id = "momentum"
            reason = "EARLY_MOMENTUM"
        elif age_minutes < 1440:
            if change_5m < -25:
                selected_id = "mean_reversion"
                reason = "OVERSOLD_BOUNCE_EXPECTED"
            elif change_5m < -15 and volume_1h > 5000:
                selected_id = "flush_recovery"
                reason = "FLUSH_RECOVERY"
            elif volume_1h > 50000 and change_5m > 5:
                selected_id = "volatility_breakout"
                reason = "BREAKOUT_DETECTED"
        else:
            if token_data.get("is_graduating", False):
                selected_id = "graduation"
                reason = "MIGRATING_TO_RAYDIUM"
            elif token_data.get("smart_money_count", 0) > 2:
                selected_id = "migration_snipe"
                reason = "SMART_MONEY_FOLLOW"

        if not selected_id:
            if age_minutes < 60:
                selected_id = "degen_ignition"
                reason = "DEFAULT_DEGEN_GATE"
            else:
                return {"status": "WATCH", "reason": "NO_STRATEGY_MATCHED_REGIME"}

        strategy_class = STRATEGY_REGISTRY.get(selected_id)
        if not strategy_class:
            return {"status": "REJECTED", "reason": "STRATEGY_NOT_FOUND"}

        try:
            strategy_instance = strategy_class()
            if hasattr(strategy_instance, "evaluate_token"):
                signal = strategy_instance.evaluate_token(token_data)
                if signal is not None:
                    return {"status": "ACCEPTED", "strategy": selected_id, "reason": reason}
            elif hasattr(strategy_instance, "should_evaluate"):
                import asyncio
                try:
                    loop = asyncio.get_event_loop()
                    is_ok = loop.run_until_complete(strategy_instance.should_evaluate(token_data))
                except RuntimeError:
                    is_ok = asyncio.run(strategy_instance.should_evaluate(token_data))
                if is_ok:
                    return {"status": "ACCEPTED", "strategy": selected_id, "reason": reason}
            
            return {"status": "WATCH", "strategy": selected_id, "reason": "REJECTED"}
        except Exception as e:
            logger.error(f"Error strategi {selected_id}: {e}")
            return {"status": "REJECTED", "reason": f"ERROR: {str(e)}"}
