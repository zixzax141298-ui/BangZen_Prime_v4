"""Durable, idempotent storage for Helius historical signature pages."""

from __future__ import annotations

from dataclasses import dataclass

from bangzen_prime.data.providers.helius_history import (
    HistoricalSignaturePage,
)
from bangzen_prime.storage.database import Database, utc_iso


@dataclass(frozen=True)
class HistoryCheckpoint:
    address: str
    before_signature: str | None
    last_signature: str | None
    last_slot: int | None
    pages_fetched: int
    coverage_status: str
    updated_at: str


class ChainHistoryStore:
    """Stores signature metadata and advances a cursor atomically."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def record_page(self, page: HistoricalSignaturePage) -> int:
        inserted = 0
        observed_at = utc_iso(page.observed_at)
        with self._db.transaction() as conn:
            for entry in page.entries:
                cursor = conn.execute(
                    "INSERT OR IGNORE INTO chain_history_signatures "
                    "(address, signature, slot, block_time, transaction_error, "
                    "confirmation_status, memo, source, observed_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        page.address,
                        entry.signature,
                        entry.slot,
                        entry.block_time,
                        int(entry.transaction_error),
                        entry.confirmation_status,
                        entry.memo,
                        page.source,
                        observed_at,
                    ),
                )
                inserted += cursor.rowcount

            current = conn.execute(
                "SELECT pages_fetched FROM chain_history_checkpoints WHERE address = ?",
                (page.address,),
            ).fetchone()
            pages = (current["pages_fetched"] if current else 0) + 1
            last_signature = (
                page.entries[-1].signature if page.entries else page.before_signature
            )
            last_slot = page.entries[-1].slot if page.entries else None
            status = "EXHAUSTED" if page.exhausted else "MORE_AVAILABLE"
            conn.execute(
                "INSERT INTO chain_history_checkpoints "
                "(address, before_signature, last_signature, last_slot, pages_fetched, "
                "coverage_status, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(address) DO UPDATE SET "
                "before_signature=excluded.before_signature, "
                "last_signature=excluded.last_signature, "
                "last_slot=excluded.last_slot, pages_fetched=excluded.pages_fetched, "
                "coverage_status=excluded.coverage_status, updated_at=excluded.updated_at",
                (
                    page.address,
                    page.next_before_signature,
                    last_signature,
                    last_slot,
                    pages,
                    status,
                    observed_at,
                ),
            )
        return inserted

    def checkpoint(self, address: str) -> HistoryCheckpoint | None:
        row = self._db.query_one(
            "SELECT * FROM chain_history_checkpoints WHERE address = ?", (address,)
        )
        if row is None:
            return None
        return HistoryCheckpoint(
            address=row["address"],
            before_signature=row["before_signature"],
            last_signature=row["last_signature"],
            last_slot=row["last_slot"],
            pages_fetched=row["pages_fetched"],
            coverage_status=row["coverage_status"],
            updated_at=row["updated_at"],
        )

    def mark_failed(self, address: str, at) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "INSERT INTO chain_history_checkpoints "
                "(address, coverage_status, updated_at) VALUES (?, 'FAILED', ?) "
                "ON CONFLICT(address) DO UPDATE SET "
                "coverage_status='FAILED', updated_at=excluded.updated_at",
                (address, utc_iso(at)),
            )

    def signature_count(self, address: str) -> int:
        row = self._db.query_one(
            "SELECT COUNT(*) AS count FROM chain_history_signatures WHERE address = ?",
            (address,),
        )
        return int(row["count"])
