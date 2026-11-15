import asyncio
import logging
import sys
import time

import httpx

from bangzen_prime.core.config import Settings
from bangzen_prime.data.retry.policies import Clock
from bangzen_prime.discovery.tokens import validate_mint
from bangzen_prime.security.smart_money_adapter import (
    SmartMoneyAdapter,
)

logger = logging.getLogger(__name__)
_INTEL_CACHE: dict[tuple[str, str], tuple[float, object]] = {}
CACHE_TTL_SECONDS = 300


def _cache_get(source: str, mint: str):
    entry = _INTEL_CACHE.get((source, mint))
    if entry is not None and time.time() - entry[0] < CACHE_TTL_SECONDS:
        return entry[1]
    return None


def _cache_put(source: str, mint: str, data: object) -> None:
    _INTEL_CACHE[(source, mint)] = (time.time(), data)


async def fetch_rugcheck_raw(mint: str):
    mint = validate_mint(
        mint
    )  # rejects path/query injection before any request is built
    cached = _cache_get("rugcheck", mint)
    if cached is not None:
        print("[*] ⚡ Mengambil data RugCheck dari Cache")
        return cached

    url = f"https://api.rugcheck.xyz/v1/tokens/{mint}/report"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=10.0)
            response.raise_for_status()
            data = response.json()

        _cache_put("rugcheck", mint, data)
        return data
    except Exception as e:
        print(f"[-] Gagal mengambil data RugCheck: {e}")
        return {}


async def fetch_solana_tracker_raw(mint: str, settings: Settings):
    mint = validate_mint(mint)
    cached = _cache_get("trades", mint)
    if cached is not None:
        print("[*] ⚡ Mengambil data Solana Tracker dari Cache")
        return cached

    url = f"https://data.solanatracker.io/tokens/{mint}/trades"

    # MENYUNTIKKAN API KEY DARI SETTINGS
    api_key = getattr(settings, "solana_tracker_api_key", "")
    headers = {"x-api-key": api_key} if api_key else {}

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, timeout=10.0)
            response.raise_for_status()
            data = response.json()

        _cache_put("trades", mint, data)
        return data
    except Exception as e:
        print(f"[-] Gagal mengambil data Solana Tracker: {e}")
        return []


async def run_intel(mint: str):
    mint = validate_mint(mint)
    settings = Settings.from_env()
    clock = Clock()

    adapter = SmartMoneyAdapter(transport=None, settings=settings, clock=clock)

    print(f"\n[*] 🚀 Menembakkan Radar Intelijen Bangzen ke target: {mint}...")
    rc_data, st_data = await asyncio.gather(
        fetch_rugcheck_raw(mint),
        fetch_solana_tracker_raw(mint, settings),  # Kirim settings ke fungsi
    )

    trades = st_data if isinstance(st_data, list) else st_data.get("trades", [])
    report = await adapter.execute_intel(mint, rc_data, trades)

    print("\n" + "=" * 45)
    print(f"🎯 LAPORAN INTELIJEN BANGZEN: {mint[:8]}...")
    print("=" * 45)
    print(f"Skor Keamanan   : {report.score}/100")
    print(f"Bundled Wallets : {'🚨 TERDETEKSI' if report.is_bundled else '✅ AMAN'}")
    print(f"MEV Predators   : {'🚨 TERDETEKSI' if report.has_mev else '✅ AMAN'}")
    print(
        f"KOL Dumping     : {'🚨 TERDETEKSI' if report.is_kol_dumping else '✅ AMAN'}"
    )
    print(f"Smart Money     : {report.sm_count} Terdeteksi")
    print(
        f"Quality Score   : {report.quality_score}/100 (Holding: {report.holding_strength})"
    )
    print(f"Rekomendasi     : 🎯 {report.recommendation}")
    print("=" * 45 + "\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Gunakan: python -m bangzen_prime.core.interfaces.intel_cli <MINT_ADDRESS>")
        sys.exit(1)
    asyncio.run(run_intel(sys.argv[1]))
