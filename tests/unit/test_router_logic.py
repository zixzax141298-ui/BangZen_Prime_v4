import asyncio
from bangzen_prime.application.strategies.base_strategy import TradingStrategy, TradeParams

class MockBase(TradingStrategy):
    def get_ai_context(self) -> str: return ""
    def get_trade_params(self) -> TradeParams: return TradeParams()
    async def should_evaluate(self, data: dict) -> bool: return True

class Sniper(MockBase): strategy_id = "sniper"
class SniperCons(MockBase): strategy_id = "sniper_conservative"
class SniperDegen(MockBase): strategy_id = "sniper_degen"
class Graduation(MockBase): strategy_id = "graduation"
class MigrationSnipe(MockBase): strategy_id = "migration_snipe"
class Momentum(MockBase): strategy_id = "momentum"
class MeanReversion(MockBase): strategy_id = "mean_reversion"
class Reversal(MockBase): strategy_id = "reversal"
class VolumeAnomaly(MockBase): strategy_id = "volume_anomaly"
class NarrativeTracker(MockBase): strategy_id = "narrative_tracker"
class DegenIgnition(MockBase): strategy_id = "degen_ignition"
class VolatilityBreakout(MockBase): strategy_id = "volatility_breakout"
class VolumeSurge(MockBase): strategy_id = "volume_surge"
class RangeRotation(MockBase): strategy_id = "range_rotation"
class FlushRecovery(MockBase): strategy_id = "flush_recovery"

class StrategyDispatcher:
    def __init__(self):
        self.weapons = {
            "sniper": Sniper(), "sniper_conservative": SniperCons(), "sniper_degen": SniperDegen(),
            "graduation": Graduation(), "migration_snipe": MigrationSnipe(), "momentum": Momentum(),
            "mean_reversion": MeanReversion(), "reversal": Reversal(), "volume_anomaly": VolumeAnomaly(),
            "narrative_tracker": NarrativeTracker(), "degen_ignition": DegenIgnition(),
            "volatility_breakout": VolatilityBreakout(), "volume_surge": VolumeSurge(),
            "range_rotation": RangeRotation(), "flush_recovery": FlushRecovery(),
        }

    async def route(self, data: dict) -> str:
        age = data.get("age_minutes", 999)
        mcap = data.get("mcap", 0)
        # PERBAIKAN: Nama variabel disamakan dengan data uji
        change_5m = data.get("change_5m", 0)
        change_1h = data.get("change_1h", 0)
        vol_1h = data.get("vol_1h", 0)
        smart_money = data.get("smart_money", 0)

        # --- FASE 1: Koin Baru (< 15 Menit) ---
        if age < 5:
            if mcap < 10000: return "sniper_degen"
            elif mcap < 50000: return "sniper"
            else: return "sniper_conservative"
        elif age < 15:
            if vol_1h > 10000: return "volume_surge"
            elif vol_1h > 5000: return "volume_anomaly"
            else: return "degen_ignition"

        # --- FASE 2: Koin Muda (15 Menit - 4 Jam) ---
        elif age < 240:
            if change_1h > 100: return "momentum"
            elif change_5m < -30: return "mean_reversion"
            elif change_5m < -15: return "flush_recovery"
            elif change_1h > 20: return "volatility_breakout"
            elif data.get("has_narrative"): return "narrative_tracker"
            else: return "reversal"

        # --- FASE 3: Koin Dewasa (> 4 Jam / Migrasi) ---
        else:
            if data.get("is_graduating"): return "graduation"
            elif smart_money > 2: return "migration_snipe"
            elif change_1h > 10: return "range_rotation"
            else: return "NO_STRATEGY"

async def run_tests():
    router = StrategyDispatcher()
    print("🧪 MENGUJI ROUTER 15 STRATEGI BANGZEN PRIME...\n")

    cases = [
        # Fase 1
        ("Koin Super Baru (Mcap 5k)", {"age_minutes": 2, "mcap": 5000, "vol_1h": 100}, "sniper_degen"),
        ("Koin Baru (Mcap 30k)", {"age_minutes": 3, "mcap": 30000, "vol_1h": 200}, "sniper"),
        ("Koin Baru (Mcap 100k)", {"age_minutes": 4, "mcap": 100000, "vol_1h": 300}, "sniper_conservative"),
        ("Koin Umur 10m (Vol Tinggi)", {"age_minutes": 10, "mcap": 20000, "vol_1h": 15000}, "volume_surge"),
        ("Koin Umur 10m (Vol Sedang)", {"age_minutes": 10, "mcap": 20000, "vol_1h": 6000}, "volume_anomaly"),
        ("Koin Umur 10m (Vol Rendah)", {"age_minutes": 10, "mcap": 20000, "vol_1h": 1000}, "degen_ignition"),
        # Fase 2 (Key 'change_1h' & 'change_5m' sudah diperbaiki)
        ("Koin 2 Jam (Naik 120%)", {"age_minutes": 120, "mcap": 80000, "change_1h": 120}, "momentum"),
        ("Koin 1 Jam (Turun 35%)", {"age_minutes": 60, "mcap": 50000, "change_5m": -35}, "mean_reversion"),
        ("Koin 1 Jam (Turun 20%)", {"age_minutes": 60, "mcap": 50000, "change_5m": -20}, "flush_recovery"),
        ("Koin 3 Jam (Naik 25%)", {"age_minutes": 180, "mcap": 200000, "change_1h": 25}, "volatility_breakout"),
        ("Koin 2 Jam (Narrative)", {"age_minutes": 120, "mcap": 50000, "has_narrative": True}, "narrative_tracker"),
        ("Koin 3 Jam (Biasa Saja)", {"age_minutes": 180, "mcap": 50000}, "reversal"),
        # Fase 3
        ("Koin Migrasi", {"age_minutes": 1441, "is_graduating": True}, "graduation"),
        ("Koin Smart Money", {"age_minutes": 1441, "smart_money": 3}, "migration_snipe"),
        ("Koin Uptrend Pelan", {"age_minutes": 1441, "change_1h": 15}, "range_rotation"),
    ]

    for name, data, expected in cases:
        selected = await router.route(data)
        status = "✅" if selected == expected else "❌"
        print(f"{status} | Data: {name:30} | Terpilih: {selected:20} (Harusnya: {expected})")

if __name__ == "__main__":
    asyncio.run(run_tests())
