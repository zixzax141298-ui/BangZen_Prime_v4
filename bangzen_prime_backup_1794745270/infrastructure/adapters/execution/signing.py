"""Signer implementations. Only DisabledSigner exists in this release.

Signing with a real key requires owner approval and a separate security review (brief, Stage 9).
DisabledSigner holds no key material and always refuses.
"""

from __future__ import annotations

from bangzen_prime.application.ports import SignedTransaction
from bangzen_prime.domain.execution import PlannedTransaction
from bangzen_prime.errors import BangzenError


class SigningDisabled(BangzenError):
    """Raised by the default signer. Chain signing is not enabled in this release."""


class DisabledSigner:
    def sign(self, plan: PlannedTransaction) -> SignedTransaction:
        raise SigningDisabled("chain signing is disabled in this release")
