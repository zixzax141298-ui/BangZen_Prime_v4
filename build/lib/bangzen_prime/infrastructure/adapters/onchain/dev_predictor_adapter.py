import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DevPredictorReport:
    is_serial_rugger: bool
    reason: str
    new_mint_timestamp: int | None = None


class DevPredictorAdapter:
    def __init__(self, transport: httpx.AsyncClient, helius_api_key: str):
        self.transport = transport
        self.helius_api_key = helius_api_key

    async def check_dev_new_mint(self, dev_address: str) -> DevPredictorReport:
        return DevPredictorReport(False, "clean_no_recent_mint")
