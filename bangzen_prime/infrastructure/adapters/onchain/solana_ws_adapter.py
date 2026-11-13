import asyncio
import json
import logging
from collections.abc import Awaitable, Callable

import websockets

from bangzen_prime.logging_utils import redact

logger = logging.getLogger(__name__)


class SolanaWebSocketAdapter:
    def __init__(self, ws_url: str, on_transaction: Callable[[dict], Awaitable[None]]):
        self.ws_url = ws_url
        self.on_transaction = on_transaction
        self.subscription_id = None

    async def _subscribe(self, websocket):
        """Berlangganan ke semua log transaksi (logsSubscribe)."""
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "logsSubscribe",
            "params": [
                "all",  # Mendengarkan semua transaksi
                {"commitment": "confirmed"},
            ],
        }
        await websocket.send(json.dumps(request))
        response = await websocket.recv()
        data = json.loads(response)
        if "result" in data:
            self.subscription_id = data["result"]
            logger.info(
                f"[*] Berhasil berlangganan ke WebSocket. ID: {self.subscription_id}"
            )
        else:
            logger.error(f"[-] Gagal berlangganan: {data}")

    async def listen(self):
        """Loop utama untuk mendengarkan pesan dari WebSocket."""
        while True:
            try:
                async with websockets.connect(self.ws_url) as websocket:
                    await self._subscribe(websocket)

                    async for message in websocket:
                        try:
                            data = json.loads(message)
                            # Filter hanya untuk notifikasi log
                            if data.get("method") == "logsNotification":
                                await self.on_transaction(
                                    data["params"]["result"]["value"]
                                )
                        except json.JSONDecodeError:
                            continue
                        except Exception as e:
                            logger.error(f"Error memproses pesan WS: {redact(str(e))}")

            except websockets.exceptions.ConnectionClosed:
                logger.warning(
                    "[!] Koneksi WebSocket terputus. Mencoba menghubungkan ulang dalam 5 detik..."
                )
                await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"[!] Error WebSocket: {redact(str(e))}. Reconnecting...")
                await asyncio.sleep(5)
