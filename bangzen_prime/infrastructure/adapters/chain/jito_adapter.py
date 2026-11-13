import logging
import random
from dataclasses import dataclass
from decimal import Decimal

import httpx

logger = logging.getLogger(__name__)

JITO_TIP_ACCOUNTS = (
    "96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5",
    "HFqU5x63VTqvQss8hp11i4wVV8bD44PvwucfZ2bU7gRe",
)


@dataclass(frozen=True)
class JitoBundleResult:
    success: bool
    bundle_id: str
    error_message: str


class JitoAdapter:
    def __init__(
        self, transport: httpx.AsyncClient, block_engine_url: str, tip_sol: Decimal
    ):
        self.transport = transport
        self.block_engine_url = block_engine_url
        self.tip_sol = tip_sol

    def pick_tip_account(self) -> str:
        return random.SystemRandom().choice(JITO_TIP_ACCOUNTS)

    async def send_jito_bundle(
        self, signed_transactions_base64: list[str]
    ) -> JitoBundleResult:
        # Logika pengiriman bundle
        return JitoBundleResult(False, "", "not_implemented_yet")
