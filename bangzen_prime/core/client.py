#!/usr/bin/env python3
"""
BANGZEN PRIME - Solana Client

The interface between BANGZEN and Solana.
Every RPC call is a question. This class asks them eloquently.
"""

import asyncio
import base64
import logging

import aiohttp
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Confirmed
from solana.rpc.types import TokenAccountOpts, TxOpts
from solders.pubkey import Pubkey
from solders.signature import Signature
from solders.transaction import Transaction, VersionedTransaction

from bangzen_prime.config import BotConfig
from bangzen_prime.core.circuit_breaker import CircuitBreaker, CircuitOpen

RPC_TIMEOUT_SECONDS = 15


class SolanaClient:
    def __init__(
        self,
        config: BotConfig,
        logger: logging.Logger,
        breaker: CircuitBreaker | None = None,
    ):
        self.config = config
        self.logger = logger
        self._breaker = breaker
        self.client = AsyncClient(config.rpc_url)
        self.pumpfun_program = Pubkey.from_string(config.pumpfun_program)

    async def _rpc(self, coro, name: str, timeout: float = RPC_TIMEOUT_SECONDS):
        try:
            if self._breaker:
                self._breaker.check()
            result = await asyncio.wait_for(coro, timeout=timeout)
            if self._breaker:
                self._breaker.record_success()
            return result
        except CircuitOpen:
            self.logger.warning(f"RPC circuit OPEN: {name}")
            return None
        except TimeoutError:
            if self._breaker:
                self._breaker.record_failure("timeout")
            self.logger.warning(f"RPC timeout: {name}")
            return None
        except Exception as e:
            if self._breaker:
                self._breaker.record_failure(type(e).__name__)
            self.logger.error(f"RPC error: {name} - {e}")
            return None

    async def get_balance(self, pubkey: Pubkey) -> float:
        resp = await self._rpc(self.client.get_balance(pubkey), "get_balance")
        return resp.value / 1e9 if resp else 0.0

    async def get_recent_signatures(self, address: Pubkey, limit: int = 10) -> list:
        resp = await self._rpc(
            self.client.get_signatures_for_address(address, limit=limit),
            "get_signatures_for_address",
        )
        return resp.value if resp and resp.value else []

    async def get_transaction(self, signature: str):
        sig = Signature.from_string(signature)
        resp = await self._rpc(
            self.client.get_transaction(
                sig,
                encoding="jsonParsed",
                commitment=Confirmed,
                max_supported_transaction_version=1,
            ),
            f"get_transaction:{signature[:16]}",
        )
        return resp.value if resp else None

    async def simulate_transaction(self, transaction: Transaction) -> bool:
        resp = await self._rpc(
            self.client.simulate_transaction(transaction, commitment=Confirmed),
            "simulate_transaction",
        )
        if resp is None:
            return False
        if resp.value.err:
            self.logger.warning(f"Simulation failed: {resp.value.err}")
            return False
        return True

    async def send_transaction(
        self, transaction: Transaction, skip_preflight: bool = False
    ) -> str | None:
        opts = TxOpts(skip_preflight=skip_preflight, preflight_commitment=Confirmed)
        resp = await self._rpc(
            self.client.send_transaction(transaction, opts), "send_transaction"
        )
        return str(resp.value) if resp else None

    async def simulate_versioned_transaction(self, raw_tx: bytes) -> bool:
        try:
            vtx = VersionedTransaction.from_bytes(raw_tx)
        except Exception as e:
            self.logger.warning(f"Could not decode versioned transaction for sim: {e}")
            return False
        resp = await self._rpc(
            self.client.simulate_transaction(vtx, commitment=Confirmed),
            "simulate_versioned_transaction",
        )
        if resp is None:
            return False
        if resp.value.err:
            self.logger.warning(f"Versioned simulation failed: {resp.value.err}")
            return False
        return True

    async def send_raw_transaction(
        self, raw_tx: bytes, skip_preflight: bool = False
    ) -> str | None:
        opts = TxOpts(skip_preflight=skip_preflight, preflight_commitment=Confirmed)
        resp = await self._rpc(
            self.client.send_raw_transaction(raw_tx, opts), "send_raw_transaction"
        )
        return str(resp.value) if resp else None

    async def get_latest_blockhash(self):
        resp = await self._rpc(
            self.client.get_latest_blockhash(commitment=Confirmed),
            "get_latest_blockhash",
        )
        return resp.value.blockhash if resp else None

    async def get_account_info(self, pubkey: Pubkey) -> bytes | None:
        resp = await self._rpc(
            self.client.get_account_info(pubkey, commitment=Confirmed),
            f"get_account_info:{pubkey}",
        )
        if resp and resp.value and resp.value.data:
            return bytes(resp.value.data)
        return None

    async def get_account_owner(self, pubkey: Pubkey) -> Pubkey | None:
        resp = await self._rpc(
            self.client.get_account_info(pubkey, commitment=Confirmed),
            f"get_account_owner:{pubkey}",
        )
        if resp and resp.value:
            return Pubkey.from_bytes(bytes(resp.value.owner))
        return None

    async def get_token_accounts_by_owner(
        self, owner: Pubkey, mint: Pubkey
    ) -> dict | None:
        resp = await self._rpc(
            self.client.get_token_accounts_by_owner_json_parsed(
                owner, TokenAccountOpts(mint=mint)
            ),
            f"get_token_accounts:{owner}",
        )
        if resp and resp.value:
            for account_info in resp.value:
                parsed = account_info.account.data.parsed
                token_amount = parsed["info"]["tokenAmount"]
                return {
                    "address": account_info.pubkey,
                    "amount": int(token_amount["amount"]),
                    "decimals": token_amount["decimals"],
                    "ui_amount": float(token_amount["uiAmount"] or 0),
                }
        return None

    async def get_token_decimals(self, mint: Pubkey) -> int | None:
        resp = await self._rpc(
            self.client.get_token_supply(mint), f"get_token_supply:{mint}"
        )
        if resp and resp.value is not None:
            return int(resp.value.decimals)
        return None

    async def get_recent_prioritization_fees(
        self, accounts: list[str] | None = None
    ) -> list[int]:
        body = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getRecentPrioritizationFees",
            "params": [accounts or []],
        }
        try:
            timeout = aiohttp.ClientTimeout(total=RPC_TIMEOUT_SECONDS)
            async with (
                aiohttp.ClientSession(trust_env=True, timeout=timeout) as session,
                session.post(self.config.rpc_url, json=body) as resp,
            ):
                if resp.status != 200:
                    return []
                data = await resp.json()
            return [int(e["prioritizationFee"]) for e in data.get("result", [])]
        except Exception as e:
            self.logger.debug(f"getRecentPrioritizationFees failed: {e}")
            return []

    async def get_signature_statuses(self, signatures: list[str]):
        sigs = [Signature.from_string(s) for s in signatures]
        resp = await self._rpc(
            self.client.get_signature_statuses(sigs), "get_signature_statuses"
        )
        return resp.value if resp and resp.value else None

    async def account_subscribe(self, pubkey: Pubkey, commitment: str = "confirmed"):
        from bangzen_prime.protocol.pumpfun import PumpFunProgram

        pumpfun = PumpFunProgram()
        rpc_url = self.config.rpc_url
        if rpc_url.startswith("https://"):
            ws_url = "wss://" + rpc_url[len("https://") :]
        elif rpc_url.startswith("http://"):
            ws_url = "ws://" + rpc_url[len("http://") :]
        else:
            ws_url = rpc_url

        backoff = 1.0
        request_id = 1
        while True:
            try:
                async with aiohttp.ClientSession(trust_env=True) as session:
                    async with session.ws_connect(ws_url) as ws:
                        await ws.send_json(
                            {
                                "jsonrpc": "2.0",
                                "id": request_id,
                                "method": "accountSubscribe",
                                "params": [
                                    str(pubkey),
                                    {"encoding": "base64", "commitment": commitment},
                                ],
                            }
                        )
                        async for msg in ws:
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                data = msg.json()
                                if "result" in data:
                                    break
                        backoff = 1.0
                        async for msg in ws:
                            if msg.type != aiohttp.WSMsgType.TEXT:
                                continue
                            data = msg.json()
                            try:
                                value = data["params"]["result"]["value"]
                                raw = value["data"][0]
                                account_data = base64.b64decode(raw)
                            except (KeyError, IndexError, TypeError, ValueError):
                                continue
                            state = pumpfun.decode_bonding_curve(account_data)
                            if state is not None:
                                yield state
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.logger.warning(
                    f"accountSubscribe reconnect in {backoff:.0f}s: {e}"
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30.0)
                request_id += 1

    async def close(self):
        await self.client.close()
