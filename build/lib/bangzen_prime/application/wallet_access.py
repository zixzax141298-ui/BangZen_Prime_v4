"""Watch-only wallet identity and fail-closed access policy.

This module accepts a public Solana address only. It never loads or stores
seed phrases, private keys, signer handles, balances, or transaction bytes.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from bangzen_prime.application.mode_controller import ModeController
from bangzen_prime.domain.operating_mode import OperatingMode
from bangzen_prime.domain.tokens import validate_mint
from bangzen_prime.errors import DomainError


class WalletAccessDenied(PermissionError):
    """Raised whenever an operation would use wallet funds or signing authority."""


class WalletRegistry:
    """Single configured watch-only public address; deliberately has no key API."""

    def __init__(self, public_address: str | None = None) -> None:
        if public_address is not None:
            try:
                validate_mint(public_address)
            except DomainError:
                raise ValueError(
                    "wallet registry accepts only a valid Solana public address"
                ) from None
        self._public_address = public_address

    def __repr__(self) -> str:
        return f"WalletRegistry(configured={self.configured}, address=[REDACTED])"

    @property
    def public_address(self) -> str | None:
        return self._public_address

    @property
    def configured(self) -> bool:
        return self._public_address is not None


@dataclass(frozen=True)
class WalletAccessSnapshot:
    mode: OperatingMode
    public_address_configured: bool
    public_address: str | None = field(repr=False)
    signer_available: bool
    funds_usable: bool
    emergency_stop_engaged: bool
    reason_codes: tuple[str, ...]


class WalletAccessController:
    """Observe wallet identity while denying signer and fund access in this release."""

    def __init__(
        self,
        *,
        registry: WalletRegistry,
        mode_controller: ModeController,
        emergency_stop: bool,
    ) -> None:
        if not isinstance(registry, WalletRegistry):
            raise TypeError("registry must be a WalletRegistry")
        if not isinstance(mode_controller, ModeController):
            raise TypeError("mode_controller must be a ModeController")
        if not isinstance(emergency_stop, bool):
            raise TypeError("emergency_stop must be bool")
        self._registry = registry
        self._mode_controller = mode_controller
        self._emergency_stop = emergency_stop

    def snapshot(self) -> WalletAccessSnapshot:
        mode = self._mode_controller.snapshot()
        reasons: list[str] = []
        if not self._registry.configured:
            reasons.append("WALLET_PUBLIC_ADDRESS_NOT_CONFIGURED")
        if mode.mode is OperatingMode.TELEGRAM_ONLY:
            reasons.append("TELEGRAM_ONLY_MODE")
        if mode.kill_switch_engaged:
            reasons.append("EXECUTION_KILL_SWITCH_ENGAGED")
        if self._emergency_stop:
            reasons.append("EMERGENCY_STOP_ENGAGED")
        if not mode.execution_available:
            reasons.append("LIVE_EXECUTION_DISABLED_BY_POLICY")
        # No signer adapter exists. This is intentionally false in every mode.
        reasons.append("SIGNER_UNAVAILABLE")
        return WalletAccessSnapshot(
            mode=mode.mode,
            public_address_configured=self._registry.configured,
            public_address=self._registry.public_address,
            signer_available=False,
            funds_usable=False,
            emergency_stop_engaged=self._emergency_stop,
            reason_codes=tuple(dict.fromkeys(reasons)),
        )

    def assert_signer_access(self) -> None:
        raise WalletAccessDenied(
            "wallet signing is disabled; no private key is available to BANGZEN"
        )

    def assert_funds_usable(self) -> None:
        raise WalletAccessDenied(
            "wallet funds are not usable by BANGZEN in this release"
        )
