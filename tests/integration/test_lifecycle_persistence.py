"""Persistence and transition invariants for the token lifecycle registry."""

import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from bangzen_prime.domain.lifecycle import LifecycleObservation, LifecyclePhase
from bangzen_prime.domain.shared import ensure_utc
from bangzen_prime.errors import DomainError
from bangzen_prime.infrastructure.persistence.sqlite.database import Database
from bangzen_prime.infrastructure.persistence.sqlite.lifecycle import LifecycleStore
from tests.support import START, TOKEN_MINT


class LifecyclePersistenceTest(unittest.TestCase):
    def make_observation(self, phase, at=START, *, reason="TEST", evidence=None):
        return LifecycleObservation(
            chain="solana",
            mint=TOKEN_MINT,
            phase=phase,
            observed_at=at,
            reason=reason,
            evidence=evidence or {},
        )

    def fresh_store(self):
        db = Database(":memory:")
        db.migrate()
        return db, LifecycleStore(db)

    def test_first_observation_is_persisted_with_one_event(self):
        db, store = self.fresh_store()
        self.assertTrue(store.observe(self.make_observation(LifecyclePhase.DISCOVERED)))
        state = store.get("solana", TOKEN_MINT)
        self.assertEqual(state["phase"], "DISCOVERED")
        self.assertEqual(state["first_seen_at"], ensure_utc(START).isoformat())
        history = store.history("solana", TOKEN_MINT)
        self.assertEqual(len(history), 1)
        self.assertIsNone(history[0]["from_phase"])
        self.assertEqual(history[0]["to_phase"], "DISCOVERED")

    def test_same_phase_updates_last_seen_without_duplicate_transition(self):
        db, store = self.fresh_store()
        store.observe(self.make_observation(LifecyclePhase.DISCOVERED))
        later = START + timedelta(seconds=30)
        self.assertTrue(store.observe(self.make_observation(LifecyclePhase.DISCOVERED, later)))
        self.assertEqual(len(store.history("solana", TOKEN_MINT)), 1)
        self.assertEqual(store.get("solana", TOKEN_MINT)["last_seen_at"],
                         ensure_utc(later).isoformat())

    def test_phase_transition_and_backward_transition_are_recorded(self):
        db, store = self.fresh_store()
        store.observe(self.make_observation(LifecyclePhase.DISCOVERED))
        store.observe(self.make_observation(
            LifecyclePhase.EXPANSION, START + timedelta(seconds=10)))
        store.observe(self.make_observation(
            LifecyclePhase.CONSOLIDATION, START + timedelta(seconds=20)))
        phases = [event["to_phase"] for event in store.history("solana", TOKEN_MINT)]
        self.assertEqual(phases, ["DISCOVERED", "EXPANSION", "CONSOLIDATION"])

    def test_stale_observation_cannot_overwrite_newer_state(self):
        db, store = self.fresh_store()
        store.observe(self.make_observation(
            LifecyclePhase.EXPANSION, START + timedelta(seconds=20)))
        accepted = store.observe(self.make_observation(
            LifecyclePhase.DISCOVERED, START + timedelta(seconds=10)))
        self.assertFalse(accepted)
        self.assertEqual(store.get("solana", TOKEN_MINT)["phase"], "EXPANSION")
        self.assertEqual(len(store.history("solana", TOKEN_MINT)), 1)

    def test_duplicate_timestamp_is_idempotently_ignored(self):
        db, store = self.fresh_store()
        observation = self.make_observation(LifecyclePhase.DISCOVERED)
        self.assertTrue(store.observe(observation))
        self.assertFalse(store.observe(observation))
        self.assertEqual(len(store.history("solana", TOKEN_MINT)), 1)

    def test_registry_survives_database_reopen(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "lifecycle.sqlite")
            first = Database(path)
            first.migrate()
            LifecycleStore(first).observe(self.make_observation(
                LifecyclePhase.EARLY_ACTIVITY, evidence={"txns_5m": 18}))
            first.close()

            reopened = Database(path)
            reopened.migrate()
            state = LifecycleStore(reopened).get("solana", TOKEN_MINT)
            self.assertEqual(state["phase"], "EARLY_ACTIVITY")
            self.assertIn('"txns_5m":18', state["evidence_json"])
            reopened.close()

    def test_invalid_mint_and_naive_timestamp_are_rejected(self):
        from datetime import datetime
        with self.assertRaises(DomainError):
            LifecycleObservation("solana", "not-a-mint", LifecyclePhase.DISCOVERED,
                                 START, "TEST", {})
        with self.assertRaises(DomainError):
            LifecycleObservation("solana", TOKEN_MINT, LifecyclePhase.DISCOVERED,
                                 datetime(2026, 1, 1), "TEST", {})

    def test_evidence_payload_is_bounded(self):
        db, store = self.fresh_store()
        with self.assertRaises(ValueError):
            store.observe(self.make_observation(
                LifecyclePhase.DISCOVERED, evidence={"payload": "x" * 17000}))

    def test_history_limit_is_validated(self):
        db, store = self.fresh_store()
        with self.assertRaises(ValueError):
            store.history("solana", TOKEN_MINT, limit=0)


if __name__ == "__main__":
    unittest.main()
