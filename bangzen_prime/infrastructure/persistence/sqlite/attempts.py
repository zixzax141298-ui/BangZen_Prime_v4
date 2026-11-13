"""Persistence for controlled chain-execution attempts."""

from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from bangzen_prime.infrastructure.persistence.sqlite.database import parse_iso, utc_iso


@dataclass(frozen=True)
class Attempt:
    id: str
    idempotency_key: str
    mode: str
    state: str
    input_mint: str
    output_mint: str
    in_amount: Decimal
    out_amount: Decimal | None
    provider: str | None
    reason: str | None
    signature: str | None
    plan_expires_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AttemptStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def create(
        self,
        *,
        idempotency_key: str,
        mode: str,
        state: str,
        input_mint: str,
        output_mint: str,
        in_amount: Decimal,
        out_amount: Decimal | None,
        provider: str | None,
        reason: str | None,
        plan_expires_at: datetime | None,
        now: datetime,
    ) -> Attempt:
        attempt_id = str(uuid.uuid4())
        self._conn.execute(
            "INSERT INTO chain_attempts (id, idempotency_key, mode, state, input_mint, output_mint,"
            " in_amount, out_amount, provider, reason, plan_expires_at, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                attempt_id,
                idempotency_key,
                mode,
                state,
                input_mint,
                output_mint,
                str(in_amount),
                str(out_amount) if out_amount is not None else None,
                provider,
                reason,
                utc_iso(plan_expires_at) if plan_expires_at else None,
                utc_iso(now),
                utc_iso(now),
            ),
        )
        return self.get(attempt_id)  # type: ignore[return-value]

    def update(
        self,
        attempt_id: str,
        *,
        state: str,
        reason: str | None = None,
        signature: str | None = None,
        now: datetime,
    ) -> None:
        self._conn.execute(
            "UPDATE chain_attempts SET state = ?, reason = ?,"
            " signature = COALESCE(?, signature), updated_at = ? WHERE id = ?",
            (state, reason, signature, utc_iso(now), attempt_id),
        )

    def get(self, attempt_id: str) -> Attempt | None:
        row = self._conn.execute(
            "SELECT * FROM chain_attempts WHERE id = ?", (attempt_id,)
        ).fetchone()
        return _row_to_attempt(row) if row else None

    def by_key(self, key: str) -> Attempt | None:
        row = self._conn.execute(
            "SELECT * FROM chain_attempts WHERE idempotency_key = ?", (key,)
        ).fetchone()
        return _row_to_attempt(row) if row else None

    def pending_reconcile(self) -> list[Attempt]:
        rows = self._conn.execute(
            "SELECT * FROM chain_attempts WHERE state IN ('SUBMITTED', 'UNKNOWN') ORDER BY created_at"
        )
        return [_row_to_attempt(r) for r in rows.fetchall()]


def _row_to_attempt(row) -> Attempt:
    return Attempt(
        id=row["id"],
        idempotency_key=row["idempotency_key"],
        mode=row["mode"],
        state=row["state"],
        input_mint=row["input_mint"],
        output_mint=row["output_mint"],
        in_amount=Decimal(row["in_amount"]),
        out_amount=(
            Decimal(row["out_amount"]) if row["out_amount"] is not None else None
        ),
        provider=row["provider"],
        reason=row["reason"],
        signature=row["signature"],
        plan_expires_at=(
            parse_iso(row["plan_expires_at"]) if row["plan_expires_at"] else None
        ),
        created_at=parse_iso(row["created_at"]),
        updated_at=parse_iso(row["updated_at"]),
    )
