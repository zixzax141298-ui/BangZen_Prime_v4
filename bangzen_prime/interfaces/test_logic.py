import asyncio
from decimal import Decimal
from datetime import datetime, timezone
from bangzen_prime.settings import Settings
from bangzen_prime.infrastructure.resilience.policies import Clock
from bangzen_prime.infrastructure.adapters.onchain.smart_money_adapter import SmartMoneyAdapter

# ==========================================
# 1. DATA PALSU (MOCK) UNTUK UJI COBA
# ==========================================

# Data RugCheck: Sengaja kita buat 3 dompet dibiayai oleh funder yang sama (Bundled!)
MOCK_RUGCHECK_BUNDLED = {
    "topHolders": [
        {"address": "wallet_A", "pct": Decimal("2.0"), "funder": "boss_dev"},
        {"address": "wallet_B", "pct": Decimal("2.0"), "funder": "boss_dev"},
        {"address": "wallet_C", "pct": Decimal("2.0"), "funder": "boss_dev"},
    ]
}

# Data Solana Tracker: Sengaja kita buat 2 MEV Predator beli, dan 1 Smart Money jual (Dumping)
now_ts = datetime.now(timezone.utc).timestamp()
MOCK_TRADES = [
    # 2 MEV Predators membeli di awal (Memicu MEV Alert)
    {"wallet": "mev_bot_1", "type": "buy", "timestamp": now_ts - 10},
    {"wallet": "mev_bot_2", "type": "buy", "timestamp": now_ts - 20},
    # 1 Smart Money menjual dalam 5 menit terakhir (Memicu KOL Dumping Alert)
    {"wallet": "smart_money_whale_1", "type": "sell", "timestamp": now_ts - 60},
]

async def run_test():
    print("\n[*] 🧪 MEMULAI UJI LOGIKA (TANPA API/INTERNET)...")
    
    # Setup Adapter
    settings = Settings.from_env()
    clock = Clock()
    adapter = SmartMoneyAdapter(transport=None, settings=settings, clock=clock)
    
    # Suntikkan daftar dompet target secara manual (karena tidak butuh file JSON untuk tes ini)
    adapter.smart_money_wallets = {"smart_money_whale_1", "smart_money_whale_2"}
    adapter.mev_wallets = {"mev_bot_1", "mev_bot_2"}

    # Jalankan analisis
    report = await adapter.execute_intel(
        mint="MOCK_MINT_ADDRESS",
        rugcheck_data=MOCK_RUGCHECK_BUNDLED,
        trades_data=MOCK_TRADES
    )

    # ==========================================
    # 2. TAMPILKAN HASIL
    # ==========================================
    print("\n" + "="*45)
    print("🎯 HASIL UJI LOGIKA BANGZEN")
    print("="*45)
    
    # Uji 1: Bundled
    status_bundled = "LULUS ✅" if report.is_bundled else "GAGAL ❌"
    print(f"[1] Deteksi Bundled : {status_bundled} (Harusnya TERDETEKSI)")
    
    # Uji 2: MEV
    status_mev = "LULUS ✅" if report.has_mev else "GAGAL ❌"
    print(f"[2] Deteksi MEV     : {status_mev} (Harusnya TERDETEKSI)")
    
    # Uji 3: Dumping
    status_dump = "LULUS ✅" if report.is_kol_dumping else "GAGAL ❌"
    print(f"[3] Deteksi Dumping : {status_dump} (Harusnya TERDETEKSI)")
    
    # Uji 4: Skor Keamanan
    # Base 100 - 50(Bundled) - 30(MEV) - 40(Dump) = 0 (Tapi kita batasi minimal 0)
    status_score = "LULUS ✅" if report.score == Decimal("0.0") else "GAGAL ❌"
    print(f"[4] Skor Keamanan   : {report.score}/100 -> {status_score} (Harusnya 0)")
    
    # Uji 5: Rekomendasi (Karena bahaya, harusnya SCALP/AVOID)
    status_rekomendasi = "LULUS ✅" if report.recommendation == "SCALP" else "GAGAL ❌"
    print(f"[5] Rekomendasi     : {report.recommendation} -> {status_rekomendasi}")
    
    print("="*45 + "\n")

if __name__ == "__main__":
    asyncio.run(run_test())
