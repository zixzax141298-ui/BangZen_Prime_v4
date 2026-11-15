"""Legacy WalletSigner compatibility shim.

This adapter used to accept a base58 private key and sign arbitrary serialized
transactions directly, bypassing ControlledExecution's quote/plan inspection,
simulation, policy checks, and persistent idempotency record.

It is intentionally disabled. The production release remains paper-only; there
is no supported path for loading a private key or signing/broadcasting a swap.
"""

from __future__ import annotations

from bangzen_prime.execution.signing import SigningDisabled


class WalletSigner:
    """Fail-closed replacement for the unsafe legacy direct signer."""

    def __init__(self, private_key_b58: str | None = None) -> None:
        # Do not decode, retain, log, or otherwise touch supplied key material.
        raise SigningDisabled(
            "legacy direct wallet signing is disabled; use the audited execution pipeline"
        )

    def sign(self, plan: object) -> str:
        """Matches the ControlledExecution call site. Always refuses."""
        raise SigningDisabled(
            "legacy direct wallet signing is disabled; transaction signing is unavailable"
        )

    def sign_transaction(self, serialized_tx_base64: str) -> str:
        """Retained only to fail closed for callers of the old interface."""
        raise SigningDisabled(
            "legacy direct wallet signing is disabled; transaction signing is unavailable"
        )
