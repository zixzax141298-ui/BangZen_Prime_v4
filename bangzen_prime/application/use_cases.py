"""Execution Use Case: Orchestrates the trading logic based on the 3 operating modes."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from bangzen_prime.application.mode_controller import ModeController
from bangzen_prime.domain.operating_mode import OperatingMode
from bangzen_prime.domain.signals import Signal, SignalStatus, RejectReason

logger = logging.getLogger(__name__)

# --- Ports (Antarmuka untuk Dependency Inversion) ---
class JupiterPort(Protocol):
    async def order(self, *, input_mint: str, output_mint: str, amount: int, taker: str) -> dict: ...
    async def execute(self, *, signed_transaction_b64: str, request_id: str) -> dict: ...

class SignerPort(Protocol):
    def sign_transaction(self, serialized_tx_base64: str) -> str: ...
    @property
    def public_key(self) -> str: ...

class HeliusPort(Protocol):
    async def simulate(self, plan: dict) -> dict: ...
    async def send(self, signed_tx: str) -> str: ...

class NotifierPort(Protocol):
    async def send(self, message: str) -> None: ...

# --- Domain Objects ---
@dataclass(frozen=True)
class ExecutionPolicy:
    paper_trading: bool
    dry_run: bool
    live_enabled: bool
    emergency_stop: bool

@dataclass(frozen=True)
class TradeResult:
    success: bool
    tx_hash: str | None
    reason: str | None
    mode: str


class ExecutionUseCase:
    def __init__(
        self,
        mode_controller: ModeController,
        policy: ExecutionPolicy,
        signer: SignerPort | None,
        jupiter: JupiterPort | None,
        helius: HeliusPort | None,
        notifier: NotifierPort | None = None,
    ) -> None:
        self._mode = mode_controller
        self._policy = policy
        self._signer = signer
        self._jupiter = jupiter
        self._helius = helius
        self._notifier = notifier

    async def execute(self, signal: Signal) -> TradeResult:
        """Main entry point to execute a trade based on the active mode."""
        
        # 1. Fail-Closed: Emergency Stop
        if self._policy.emergency_stop:
            logger.warning("EXECUTION BLOCKED: Emergency stop is active.")
            return TradeResult(False, None, "EMERGENCY_STOP_ACTIVE", self._mode.value)

        # 2. Fail-Closed: Check if signal is valid for execution
        if signal.status != SignalStatus.ACCEPTED:
            return TradeResult(False, None, "SIGNAL_NOT_ACCEPTED", self._mode.value)

        # 3. Mode Routing
        current_mode = self._mode.mode
        
        if current_mode == OperatingMode.TELEGRAM_ONLY:
            logger.info(f"SIGNAL_ONLY: Not executing {signal.token_id}. Sending to Telegram only.")
            await self._send_notification(signal, "SIGNAL_ONLY")
            return TradeResult(True, None, "TELEGRAM_ONLY", current_mode.value)

        if current_mode in (OperatingMode.EXECUTION_ONLY, OperatingMode.HYBRID):
            # Check Live Trading readiness
            if not self._policy.live_enabled or not self._signer or not self._jupiter or not self._helius:
                logger.error("EXECUTION FAILED: Missing dependencies (Signer/Jupiter/Helius) or Live Trading disabled.")
                return TradeResult(False, None, "MISSING_EXECUTION_DEPENDENCIES", current_mode.value)

            # Execute the trade
            result = await self._execute_live_trade(signal)
            
            # If HYBRID, send notification after execution
            if current_mode == OperatingMode.HYBRID:
                if result.success:
                    await self._send_notification(signal, f"EXECUTED_SUCCESS | TX: {result.tx_hash}")
                else:
                    await self._send_notification(signal, f"EXECUTION_FAILED | Reason: {result.reason}")
                    
            return result

        logger.error(f"UNKNOWN MODE: {current_mode}")
        return TradeResult(False, None, "UNKNOWN_MODE", "UNKNOWN")

    async def _execute_live_trade(self, signal: Signal) -> TradeResult:
        """Orchestrates the actual on-chain swap."""
        try:
            # 1. Create Order (Jupiter)
            # Note: You need to calculate the actual amount based on your portfolio/risk logic.
            # Here we use a dummy amount for the skeleton.
            amount = 1000000  # Example: 1 USDC in micro-lamports
            order = await self._jupiter.order(
                input_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", # USDC
                output_mint=signal.token_id,
                amount=amount,
                taker=self._signer.public_key
            )
            
            # 2. Sign Transaction (WalletSigner)
            signed_tx = self._signer.sign_transaction(order["transaction"])
            
            # 3. Simulate Transaction (Helius) - CRITICAL SAFETY GATE
            sim_result = await self._helius.simulate({"signed_transaction": signed_tx})
            if not sim_result.get("success"):
                logger.error(f"SIMULATION FAILED: {sim_result.get('error')}")
                return TradeResult(False, None, "SIMULATION_FAILED", self._mode.mode.value)

            # 4. Broadcast Transaction (Helius)
            tx_hash = await self._helius.send(signed_tx)
            
            logger.info(f"EXECUTION SUCCESS: TX Hash {tx_hash}")
            return TradeResult(True, tx_hash, None, self._mode.mode.value)

        except Exception as exc:
            logger.exception("EXECUTION ERROR during live trade")
            return TradeResult(False, None, str(exc), self._mode.mode.value)

    async def _send_notification(self, signal: Signal, status_msg: str):
        if self._notifier:
            try:
                msg = (
                    f"🚀 [BANGZEN PRIME] {status_msg}\n"
                    f"Token: {signal.token_id}\n"
                    f"Score: {signal.score}\n"
                    f"Mode: {self._mode.mode.value}"
                )
                await self._notifier.send(msg)
            except Exception as e:
                logger.error(f"Failed to send notification: {e}")
