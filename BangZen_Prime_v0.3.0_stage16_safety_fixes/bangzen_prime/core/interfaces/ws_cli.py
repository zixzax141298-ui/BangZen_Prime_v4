import asyncio
import logging

from bangzen_prime.core.config import Settings
from bangzen_prime.core.logging_utils import configure_logging, redact
from bangzen_prime.data.providers.solana_ws_adapter import (
    SolanaWebSocketAdapter,
)
from bangzen_prime.risk.emergency_stop import HALT_FLAG_PATH, halt_flag_engaged

_HALT_PATH = HALT_FLAG_PATH

logger = logging.getLogger("bangzen_prime.core.interfaces.ws_cli")

# Daftar dompet Smart Money (sementara hardcode untuk testing)
SMART_MONEY_WALLETS = {
    "5Q544fKrFoe6tsEbD7S8EmxGTJYAKtTVhAW5Q5pge4j1",  # Contoh: Alamat Raydium (ganti dengan target Anda)
}


async def handle_transaction(tx_data: dict):
    """Callback yang dipanggil setiap ada transaksi baru."""
    if halt_flag_engaged(_HALT_PATH):  # HALT.flag can appear while the listener is running
        return
    try:
        account_keys = (
            tx_data.get("transaction", {}).get("message", {}).get("accountKeys", [])
        )
        involved_wallets = set(account_keys).intersection(SMART_MONEY_WALLETS)

        if involved_wallets:
            signature = tx_data.get("signature", "N/A")
            logger.info(
                f"🚨 SMART MONEY DETECTED! Wallet: {involved_wallets} | Tx: {signature}"
            )

    except Exception as e:
        logger.error(f"Error handling transaction: {redact(str(e))}")


async def main():
    settings = Settings.from_env()
    if settings.halt_active():
        logger.error(
            "HALT engaged (BANGZEN_EMERGENCY_STOP=true or HALT.flag present); WebSocket listener not started"
        )
        return

    # Validasi API Key sebelum mencoba konek
    if not settings.helius_api_key or len(settings.helius_api_key.strip()) < 10:
        logger.error(
            "❌ HELIUS_API_KEY tidak ditemukan atau tidak valid di .env. WebSocket tidak bisa berjalan."
        )
        return

    # Format URL WebSocket yang benar untuk Helius
    ws_url = f"wss://mainnet.helius-rpc.com/?api-key={settings.helius_api_key.strip()}"
    logger.info("[*] Mencoba terhubung ke WebSocket Helius...")

    adapter = SolanaWebSocketAdapter(ws_url, on_transaction=handle_transaction)

    try:
        await adapter.listen()
    except Exception as e:
        logger.error(f"❌ Gagal total: {redact(str(e))}")


if __name__ == "__main__":
    configure_logging("INFO")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Radar dihentikan oleh Owner.")
