import logging
from dataclasses import dataclass
from datetime import datetime
import httpx

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class KOLExitReport:
    is_kol_selling: bool
    status: str
    reason: str

class KOLExitAdapter:
    def __init__(self, transport: httpx.AsyncClient, helius_rpc_url: str, smart_money_wallets: set[str]):
        self.transport = transport
        self.helius_rpc_url = helius_rpc_url
        self.smart_money_wallets = smart_money_wallets

    async def check_kol_exit(self, token_address: str, now: datetime) -> KOLExitReport:
        return KOLExitReport(False, "CLEAN", "")
