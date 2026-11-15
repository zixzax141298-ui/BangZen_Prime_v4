"""Signer implementations. Only DisabledSigner exists in this release.

Signing with a real key requires owner approval and a separate security review (brief, Stage 9).
DisabledSigner holds no key material and always refuses.
"""

from __future__ import annotations

from bangzen_prime.core.errors import BangzenError
from bangzen_prime.core.ports import SignedTransaction
from bangzen_prime.execution.execution import PlannedTransaction


class SigningDisabled(BangzenError):
    """Raised by the default signer. Chain signing is not enabled in this release."""


class DisabledSigner:
    def sign(self, plan: PlannedTransaction) -> SignedTransaction:
        raise SigningDisabled("chain signing is disabled in this release")
