"""Read-only Helius WebSocket logs ingestion.

This module emits validated observations only. It does not infer token safety,
replay history, sign transactions, or broadcast transactions. Consumers must
persist checkpoints and reconcile disconnect gaps through HTTP history APIs.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode


_ADDRESS_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")
_MAX_MESSAGE_BYTES = 1_048_576


class HeliusStreamError(RuntimeError):
    """Base error that never includes the credential-bearing endpoint."""


class HeliusStreamProtocolError(HeliusStreamError):
    """The upstream sent an invalid JSON-RPC message."""


class HeliusStreamUnavailable(HeliusStreamError):
    """The WebSocket could not be kept connected within the retry budget."""


@dataclass(frozen=True)
class HeliusWebSocketConfig:
    api_key: str = field(repr=False)
    endpoint: str = "wss://mainnet.helius-rpc.com"
    timeout_seconds: float = 10.0
    max_reconnect_attempts: int = 5
    reconnect_base_delay_seconds: float = 0.5
    commitment: str = "confirmed"

    def __post_init__(self) -> None:
        if not self.api_key or not self.api_key.strip():
            raise ValueError("Helius API key is required")
        if not self.endpoint.startswith("wss://") or "?" in self.endpoint:
            raise ValueError("Helius WebSocket endpoint must be a clean wss:// URL")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.max_reconnect_attempts < 0:
            raise ValueError("max_reconnect_attempts cannot be negative")
        if self.reconnect_base_delay_seconds < 0:
            raise ValueError("reconnect delay cannot be negative")
        if self.commitment not in {"processed", "confirmed", "finalized"}:
            raise ValueError("unsupported Solana commitment")


@dataclass(frozen=True)
class HeliusLogEvent:
    slot: int
    signature: str
    transaction_failed: bool
    logs: tuple[str, ...]


@dataclass(frozen=True)
class HeliusStreamGap:
    """Emitted after reconnect; downstream must reconcile missed slots/history."""

    reconnect_number: int
    reason: str = "websocket_reconnected_history_reconciliation_required"


StreamItem = HeliusLogEvent | HeliusStreamGap


def build_logs_subscribe_request(address: str, commitment: str = "confirmed") -> dict[str, Any]:
    if not isinstance(address, str) or not _ADDRESS_RE.fullmatch(address):
        raise ValueError("invalid Solana address for logsSubscribe")
    if commitment not in {"processed", "confirmed", "finalized"}:
        raise ValueError("unsupported Solana commitment")
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "logsSubscribe",
        "params": [{"mentions": [address]}, {"commitment": commitment}],
    }


def parse_logs_notification(payload: Any) -> HeliusLogEvent | None:
    """Parse one logsNotification. Non-notification JSON-RPC messages are ignored."""
    if not isinstance(payload, dict) or payload.get("method") != "logsNotification":
        return None
    try:
        result = payload["params"]["result"]
        context = result["context"]
        value = result["value"]
        slot = context["slot"]
        signature = value["signature"]
        logs = value["logs"]
        error = value.get("err")
    except (KeyError, TypeError):
        raise HeliusStreamProtocolError("malformed Helius logs notification") from None

    if isinstance(slot, bool) or not isinstance(slot, int) or slot < 0:
        raise HeliusStreamProtocolError("invalid slot in Helius notification")
    if not isinstance(signature, str) or not signature or len(signature) > 128:
        raise HeliusStreamProtocolError("invalid signature in Helius notification")
    if not isinstance(logs, list) or any(not isinstance(line, str) for line in logs):
        raise HeliusStreamProtocolError("invalid logs in Helius notification")
    return HeliusLogEvent(
        slot=slot,
        signature=signature,
        transaction_failed=error is not None,
        logs=tuple(logs),
    )


class HeliusWebSocketStream:
    """Reconnectable, read-only logsSubscribe stream.

    A gap marker is emitted after every successful reconnection. This client
    does not claim gap-free delivery or historical completeness.
    """

    def __init__(
        self,
        config: HeliusWebSocketConfig,
        *,
        connector: Callable[..., Any] | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._config = config
        self._connector = connector
        self._sleep = sleep

    def _url(self) -> str:
        return f"{self._config.endpoint.rstrip('/')}/?{urlencode({'api-key': self._config.api_key})}"

    def _get_connector(self) -> Callable[..., Any]:
        if self._connector is not None:
            return self._connector
        try:
            from websockets.asyncio.client import connect
        except ImportError:
            try:
                from websockets import connect
            except ImportError:
                raise HeliusStreamUnavailable(
                    "websockets package is required; install the ws extra"
                ) from None
        return connect

    async def events_for_address(self, address: str) -> AsyncIterator[StreamItem]:
        request = build_logs_subscribe_request(address, self._config.commitment)
        connector = self._get_connector()
        consecutive_failures = 0
        reconnect_number = 0
        connected_before = False

        while True:
            try:
                async with connector(
                    self._url(),
                    open_timeout=self._config.timeout_seconds,
                    ping_interval=20,
                    ping_timeout=20,
                    close_timeout=5,
                    max_size=_MAX_MESSAGE_BYTES,
                ) as websocket:
                    await websocket.send(json.dumps(request, separators=(",", ":")))
                    acknowledgement = json.loads(await websocket.recv())
                    if (
                        not isinstance(acknowledgement, dict)
                        or acknowledgement.get("id") != 1
                        or isinstance(acknowledgement.get("result"), bool)
                        or not isinstance(acknowledgement.get("result"), int)
                    ):
                        raise HeliusStreamProtocolError(
                            "invalid logsSubscribe acknowledgement"
                        )

                    if connected_before:
                        reconnect_number += 1
                        yield HeliusStreamGap(reconnect_number=reconnect_number)
                    connected_before = True

                    async for raw_message in websocket:
                        if not isinstance(raw_message, str):
                            raise HeliusStreamProtocolError(
                                "binary WebSocket messages are not supported"
                            )
                        if len(raw_message.encode("utf-8")) > _MAX_MESSAGE_BYTES:
                            raise HeliusStreamProtocolError(
                                "Helius WebSocket message exceeds size limit"
                            )
                        try:
                            payload = json.loads(raw_message)
                        except json.JSONDecodeError:
                            raise HeliusStreamProtocolError(
                                "invalid JSON from Helius WebSocket"
                            ) from None
                        event = parse_logs_notification(payload)
                        if event is not None:
                            consecutive_failures = 0
                            yield event
                    # A clean server-side close is still a stream interruption.
                    raise ConnectionError("Helius WebSocket closed")

            except asyncio.CancelledError:
                raise
            except HeliusStreamProtocolError:
                raise
            except Exception:
                consecutive_failures += 1
                if consecutive_failures > self._config.max_reconnect_attempts:
                    raise HeliusStreamUnavailable(
                        "Helius WebSocket reconnect budget exhausted"
                    ) from None
                delay = min(
                    self._config.reconnect_base_delay_seconds
                    * (2 ** (consecutive_failures - 1)),
                    30.0,
                )
                await self._sleep(delay)
