"""Repositories and unit of work. All writes for one use case share one transaction."""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from bangzen_prime.discovery.tokens import PairSnapshot, SafetyAssessment, Token
from bangzen_prime.scoring.signals import (
    PriceLevels,
    RejectReason,
    Signal,
    SignalStatus,
)
from bangzen_prime.storage.attempts import AttemptStore
from bangzen_prime.storage.database import (
    Database,
    parse_iso,
    utc_iso,
)
from bangzen_prime.storage.outbox import AuditLog, OutboxStore


class TokenRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def upsert(self, token: Token, at: datetime) -> None:
        self._conn.execute(
            "INSERT INTO tokens (id, chain, mint, symbol, name, created_at) VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET symbol = excluded.symbol, name = excluded.name",
            (
                str(token.id),
                token.chain,
                token.mint,
                token.symbol,
                token.name,
                utc_iso(at),
            ),
        )

    def get_by_mint(self, chain: str, mint: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM tokens WHERE chain = ? AND mint = ?", (chain, mint)
        ).fetchone()
        return dict(row) if row else None


class PairRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def upsert(self, pair: PairSnapshot) -> None:
        self._conn.execute(
            "INSERT INTO pairs (id, token_id, chain, pair_address, dex_id, price_usd, liquidity_usd,"
            " volume_24h_usd, observed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET price_usd = excluded.price_usd,"
            " liquidity_usd = excluded.liquidity_usd, volume_24h_usd = excluded.volume_24h_usd,"
            " observed_at = excluded.observed_at",
            (
                str(pair.pair_id),
                str(pair.token_id),
                pair.chain,
                pair.pair_address,
                pair.dex_id,
                str(pair.price_usd),
                str(pair.liquidity_usd),
                str(pair.volume_24h_usd),
                utc_iso(pair.observed_at),
            ),
        )


class PriceRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def append(self, token_id: uuid.UUID, price: Decimal, at: datetime) -> None:
        self._conn.execute(
            "INSERT INTO price_samples (token_id, price_usd, observed_at) VALUES (?, ?, ?)",
            (str(token_id), str(price), utc_iso(at)),
        )

    def recent(self, token_id: uuid.UUID, limit: int) -> list[Decimal]:
        """Return the most recent `limit` prices in chronological order."""
        rows = self._conn.execute(
            "SELECT price_usd FROM price_samples WHERE token_id = ? ORDER BY id DESC LIMIT ?",
            (str(token_id), limit),
        ).fetchall()
        return [Decimal(row["price_usd"]) for row in reversed(rows)]


class SafetyRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def append(self, token_id: uuid.UUID, assessment: SafetyAssessment) -> None:
        self._conn.execute(
            "INSERT INTO safety_checks (token_id, risk_score, rugged, source, checked_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (
                str(token_id),
                str(assessment.risk_score),
                int(assessment.rugged),
                assessment.source,
                utc_iso(assessment.checked_at),
            ),
        )


class SignalRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def add(self, signal: Signal) -> None:
        levels = signal.levels
        self._conn.execute(
            "INSERT INTO signals (id, token_id, pair_id, status, score, entry_price, stop_loss,"
            " take_profit, confidence, reasons, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(signal.id),
                str(signal.token_id),
                str(signal.pair_id),
                signal.status.value,
                str(signal.score),
                str(levels.entry) if levels else None,
                str(levels.stop_loss) if levels else None,
                str(levels.take_profit) if levels else None,
                str(signal.confidence) if signal.confidence is not None else None,
                json.dumps([r.value for r in signal.reasons]),
                utc_iso(signal.created_at),
            ),
        )

    def get(self, signal_id: uuid.UUID) -> Signal | None:
        row = self._conn.execute(
            "SELECT * FROM signals WHERE id = ?", (str(signal_id),)
        ).fetchone()
        if row is None:
            return None
        levels = None
        if row["status"] == SignalStatus.ACCEPTED.value:
            levels = PriceLevels(
                Decimal(row["entry_price"]),
                Decimal(row["stop_loss"]),
                Decimal(row["take_profit"]),
            )
        return Signal(
            signal_id=uuid.UUID(row["id"]),
            token_id=uuid.UUID(row["token_id"]),
            pair_id=uuid.UUID(row["pair_id"]),
            status=SignalStatus(row["status"]),
            score=Decimal(row["score"]),
            reasons=tuple(RejectReason(r) for r in json.loads(row["reasons"])),
            created_at=parse_iso(row["created_at"]),
            levels=levels,
            confidence=(
                Decimal(row["confidence"]) if row["confidence"] is not None else None
            ),
        )

    def count_by_status(self, status: SignalStatus) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM signals WHERE status = ?", (status.value,)
        ).fetchone()
        return int(row["n"])


@dataclass
class Repositories:
    tokens: TokenRepository
    pairs: PairRepository
    prices: PriceRepository
    safety: SafetyRepository
    signals: SignalRepository
    outbox: OutboxStore
    audit: AuditLog
    attempts: AttemptStore


class UnitOfWork:
    """Opens one serialised transaction and hands out repositories bound to it."""

    def __init__(self, db: Database) -> None:
        self._db = db

    @contextmanager
    def begin(self) -> Iterator[Repositories]:
        with self._db.transaction() as conn:
            yield Repositories(
                tokens=TokenRepository(conn),
                pairs=PairRepository(conn),
                prices=PriceRepository(conn),
                safety=SafetyRepository(conn),
                signals=SignalRepository(conn),
                outbox=OutboxStore(conn),
                audit=AuditLog(conn),
                attempts=AttemptStore(conn),
            )
