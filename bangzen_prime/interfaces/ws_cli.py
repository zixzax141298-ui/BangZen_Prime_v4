import asyncio
import logging

from bangzen_prime.infrastructure.adapters.onchain.solana_ws_adapter import (
    SolanaWebSocketAdapter,
)
from bangzen_prime.logging_utils import configure_logging, redact
from bangzen_prime.settings import Settings

logger = logging.getLogger("bangzen_prime.interfaces.ws_cli")

# Daftar dompet Smart Money (sementara hardcode untuk testing)
SMART_MONEY_WALLETS = {
    "5Q544fKrFoe6tsEbD7S8EmxGTJYAKtTVhAW5Q5pge4j1",  # Contoh: Alamat Raydium (ganti dengan target Anda)
}


async def handle_transaction(tx_data: dict):
    """Callback yang dipanggil setiap ada transaksi baru."""
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
