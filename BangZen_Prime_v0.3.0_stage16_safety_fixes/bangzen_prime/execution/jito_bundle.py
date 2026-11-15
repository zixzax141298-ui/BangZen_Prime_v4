"""Jito tip transaction and optional bundle relay.

Signing and tip-transaction construction remain locked after removal of the
plaintext burner wallet. `relay_bundle` still posts JSON-RPC `sendBundle` only
when the caller passes `allow_broadcast=True`. The default refuses, matching the
locked broadcast flag in settings.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from bangzen_prime.core.errors import BangzenError
from bangzen_prime.data.http import (
    HttpRequest,
    RequestTransport,
    request_json,
)
from bangzen_prime.data.retry.policies import ResilientCaller
from bangzen_prime.execution.signing import SigningDisabled

_SERVICE = "jito"


class BroadcastRefused(BangzenError):
    """Raised when a bundle would be sent without an explicit allow_broadcast=True."""


@dataclass(frozen=True)
class SignedBundle:
    transactions_b64: tuple[str, ...]
    tip_lamports: int
    signer: str


def build_tip_transaction(
    wallet: object,
    *,
    tip_account: str,
    tip_lamports: int,
    recent_blockhash: str,
) -> str:
    """Fail-closed: local tip transaction construction requires a removed burner wallet."""
    raise SigningDisabled(
        "tip transaction construction is disabled; plaintext burner wallet was removed"
    )


def relay_bundle(
    transactions_b64: list[str],
    *,
    transport: RequestTransport,
    caller: ResilientCaller,
    timeout: float,
    block_engine: str,
    allow_broadcast: bool = False,
) -> str:
    """POST sendBundle. Refuses unless allow_broadcast is True. Returns the bundle id."""
    if not allow_broadcast:
        raise BroadcastRefused("bundle relay is refused unless allow_broadcast=True")
    if not 1 <= len(transactions_b64) <= 5:
        raise ValueError("a bundle holds 1 to 5 transactions")
    body = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "sendBundle",
            "params": [transactions_b64, {"encoding": "base64"}],
        }
    ).encode("utf-8")
    request = HttpRequest(
        "POST",
        block_engine,
        {"Content-Type": "application/json"},
        body,
        timeout,
    )
    payload = caller.call(
        lambda: request_json(service=_SERVICE, request=request, transport=transport)
    )
    result = payload.get("result") if isinstance(payload, dict) else None
    if not isinstance(result, str) or not result:
        raise ValueError("jito sendBundle returned no bundle id")
    return result
