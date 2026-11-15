"""Wallet diagnostics are intentionally keyless in this paper-only release.

The previous command loaded BANGZEN_BURNER_PRIVATE_KEY into a direct signer.
That created a separate secret-loading path outside ControlledExecution.
No wallet key is loaded, validated, printed, or signed by this command.
"""

from __future__ import annotations


def main() -> int:
    print("BANGZEN PRIME — WALLET DIAGNOSTICS")
    print("LOCKED: this release is paper-only.")
    print("No private key was loaded. Signing and live broadcast are unavailable.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
