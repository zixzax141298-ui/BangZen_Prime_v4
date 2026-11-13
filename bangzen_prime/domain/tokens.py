"""Token, trading pair, and safety assessment. Identity is deterministic per chain+address."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from bangzen_prime.domain.shared import AggregateRoot, ensure_utc
from bangzen_prime.domain.values import non_negative, percent, positive
from bangzen_prime.errors import DomainError

SUPPORTED_CHAINS = frozenset({"solana"})
_BASE58_ADDRESS = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")
_IDENTITY_NAMESPACE = uuid.UUID("6f1d2c5a-3b8e-4f7a-9c2d-0a1b2c3d4e5f")


def validate_chain(chain: str) -> str:
    if chain not in SUPPORTED_CHAINS:
        raise DomainError(f"unsupported chain: {chain!r}")
    return chain


def validate_mint(mint: str) -> str:
    if not isinstance(mint, str) or not _BASE58_ADDRESS.match(mint):
        raise DomainError("token address is not a valid base58 Solana address")
    return mint


def token_identity(chain: str, address: str) -> uuid.UUID:
    """Same chain+address always yields the same UUID, across every use case."""
    return uuid.uuid5(_IDENTITY_NAMESPACE, f"{validate_chain(chain)}:{validate_mint(address)}")


def pair_identity(chain: str, pair_address: str) -> uuid.UUID:
    if not isinstance(pair_address, str) or not pair_address.strip():
        raise DomainError("pair address must not be empty")
    return uuid.uuid5(_IDENTITY_NAMESPACE, f"pair:{validate_chain(chain)}:{pair_address.strip()}")


class Token(AggregateRoot):
    def __init__(self, *, chain: str, mint: str, symbol: str, name: str = "") -> None:
        validate_chain(chain)
        validate_mint(mint)
        if not symbol or len(symbol) > 32 or not symbol.isprintable():
            raise DomainError("token symbol must be 1-32 printable characters")
        super().__init__(token_identity(chain, mint))
        self.chain = chain
        self.mint = mint
        self.symbol = symbol
        self.name = name[:128]


@dataclass(frozen=True)
class PairSnapshot:
    """Market observation of one DEX pair, including optional pair creation evidence."""

    chain: str
    pair_address: str
    dex_id: str
    base_mint: str
    base_symbol: str
    price_usd: Decimal
    liquidity_usd: Decimal
    volume_24h_usd: Decimal
    observed_at: datetime
    pair_created_at: datetime | None = None
    source: str = "UNSPECIFIED"

    @classmethod
    def create(
        cls, *, chain: str, pair_address: str, dex_id: str, base_mint: str,
        base_symbol: str, price_usd: object, liquidity_usd: object,
        volume_24h_usd: object, observed_at: datetime,
        pair_created_at: datetime | None = None,
        source: str = "UNSPECIFIED",
    ) -> PairSnapshot:
        validate_chain(chain)
        validate_mint(base_mint)
        if not isinstance(pair_address, str) or not pair_address.strip() or not isinstance(dex_id, str) or not dex_id.strip():
            raise DomainError("pair address and dex id must not be empty")
        if not isinstance(source, str) or not source.strip() or len(source) > 64 or not source.isprintable():
            raise DomainError("market source must be a non-empty printable value of at most 64 characters")
        return cls(
            chain=chain,
            pair_address=pair_address.strip(),
            dex_id=dex_id.strip(),
            base_mint=base_mint,
            base_symbol=base_symbol,
            price_usd=positive(price_usd, "price_usd"),
            liquidity_usd=non_negative(liquidity_usd, "liquidity_usd"),
            volume_24h_usd=non_negative(volume_24h_usd, "volume_24h_usd"),
            observed_at=ensure_utc(observed_at),
            pair_created_at=ensure_utc(pair_created_at) if pair_created_at is not None else None,
            source=source.strip(),
        )

    @property
    def pair_id(self) -> uuid.UUID:
        return pair_identity(self.chain, self.pair_address)

    @property
    def token_id(self) -> uuid.UUID:
        return token_identity(self.chain, self.base_mint)

    def is_stale(self, now: datetime, max_age_seconds: int) -> bool:
        age = (ensure_utc(now) - self.observed_at).total_seconds()
        return age < 0 or age > max_age_seconds


@dataclass(frozen=True)
class SafetyAssessment:
    """Normalised safety result. risk_score: 0 = lowest risk, 100 = highest, higher is riskier."""

    chain: str
    mint: str
    risk_score: Decimal
    rugged: bool
    source: str
    checked_at: datetime

    @classmethod
    def create(cls, *, chain: str, mint: str, risk_score: object, rugged: bool,
               source: str, checked_at: datetime) -> SafetyAssessment:
        validate_chain(chain)
        validate_mint(mint)
        if not isinstance(rugged, bool):
            raise DomainError("rugged must be a boolean")
        return cls(chain, mint, percent(risk_score, "risk_score"), rugged, source,
                   ensure_utc(checked_at))

    def rejection_reason(self, max_risk_score: Decimal) -> str | None:
        """Return a reason code if the token must not proceed to scoring."""
        if self.rugged:
            return "RUGGED"
        if self.risk_score > max_risk_score:
            return "RISK_TOO_HIGH"
        return None
