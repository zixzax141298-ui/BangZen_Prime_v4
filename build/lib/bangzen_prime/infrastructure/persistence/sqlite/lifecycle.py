"""Persistent lifecycle registry with monotonic observation ordering and phase history."""

from __future__ import annotations

import json
from typing import Any

from bangzen_prime.domain.lifecycle import LifecycleObservation
from bangzen_prime.infrastructure.persistence.sqlite.database import (
    Database,
    parse_iso,
    utc_iso,
)


class LifecycleStore:
    """Stores the latest state and append-only phase transitions across restarts."""

    def __init__(self, db: Database) -> None:
        self._db = db

    @staticmethod
    def _encode_evidence(evidence: dict[str, Any]) -> str:
        encoded = json.dumps(
            evidence, sort_keys=True, separators=(",", ":"), default=str
        )
        if len(encoded.encode("utf-8")) > 16_384:
            raise ValueError("lifecycle evidence exceeds 16 KiB")
        return encoded

    def observe(self, observation: LifecycleObservation) -> bool:
        """Persist a newer observation; return False for stale or duplicate timestamps."""
        evidence_json = self._encode_evidence(observation.evidence)
        observed_at = utc_iso(observation.observed_at)
        with self._db.transaction() as conn:
            row = conn.execute(
                "SELECT phase, last_observed_at FROM token_lifecycle "
                "WHERE chain = ? AND mint = ?",
                (observation.chain, observation.mint),
            ).fetchone()
            if row is not None and observation.observed_at <= parse_iso(
                row["last_observed_at"]
            ):
                return False

            previous = row["phase"] if row is not None else None
            if row is None:
                conn.execute(
                    "INSERT INTO token_lifecycle "
                    "(chain, mint, phase, first_seen_at, last_seen_at, last_observed_at, "
                    "reason, evidence_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        observation.chain,
                        observation.mint,
                        observation.phase.value,
                        observed_at,
                        observed_at,
                        observed_at,
                        observation.reason,
                        evidence_json,
                    ),
                )
            else:
                conn.execute(
                    "UPDATE token_lifecycle SET phase = ?, last_seen_at = ?, "
                    "last_observed_at = ?, reason = ?, evidence_json = ? "
                    "WHERE chain = ? AND mint = ?",
                    (
                        observation.phase.value,
                        observed_at,
                        observed_at,
                        observation.reason,
                        evidence_json,
                        observation.chain,
                        observation.mint,
                    ),
                )

            if previous != observation.phase.value:
                conn.execute(
                    "INSERT INTO token_lifecycle_events "
                    "(chain, mint, from_phase, to_phase, observed_at, reason, evidence_json) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        observation.chain,
                        observation.mint,
                        previous,
                        observation.phase.value,
                        observed_at,
                        observation.reason,
                        evidence_json,
                    ),
                )
            return True

    def get(self, chain: str, mint: str) -> dict[str, Any] | None:
        row = self._db.query_one(
            "SELECT * FROM token_lifecycle WHERE chain = ? AND mint = ?",
            (chain, mint),
        )
        return dict(row) if row is not None else None

    def history(
        self, chain: str, mint: str, *, limit: int = 100
    ) -> list[dict[str, Any]]:
        if not 1 <= limit <= 1000:
            raise ValueError("history limit must be within [1, 1000]")
        rows = self._db.query_all(
            "SELECT * FROM token_lifecycle_events WHERE chain = ? AND mint = ? "
            "ORDER BY id DESC LIMIT ?",
            (chain, mint, limit),
        )
        return [dict(row) for row in reversed(rows)]
