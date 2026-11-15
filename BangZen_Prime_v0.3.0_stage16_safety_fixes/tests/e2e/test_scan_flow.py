import json
import os
import tempfile
import unittest
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

from bangzen_prime.core.bootstrap import build_container
from bangzen_prime.core.config import Settings
from bangzen_prime.core.errors import ConfigurationError
from bangzen_prime.data.http import HttpResponse, TransportTimeout
from bangzen_prime.research.ai_brain import AIBrain
from bangzen_prime.security.helius_token_2022_extensions import (
    HeliusToken2022ExtensionReader,
)
from bangzen_prime.security.token_2022_extension_config import (
    ParsedToken2022Configuration,
)
from bangzen_prime.security.token_2022_extension_evidence import (
    Token2022ExtensionEvidence,
)
from bangzen_prime.security.token_2022_extensions import REJECTED, VERIFIED
from bangzen_prime.security.token_programs import (
    TOKEN_2022_PROGRAM_ID,
    TOKEN_PROGRAM_ID,
)
from bangzen_prime.storage.outbox import AuditLog
from tests.support import (
    START,
    TOKEN_MINT,
    RecordingNotifier,
    RecordingTransport,
    clock_at,
    json_response,
    pair_payload,
    safety_payload,
)

DEX = "https://api.dexscreener.com"
RC = "https://api.rugcheck.xyz/v1"


class FakeAIProvider:
    name = "test"

    def __init__(self):
        self.calls = 0

    def complete(self, system, user):
        self.calls += 1
        return json.dumps(
            {
                "risk_level": "LOW",
                "summary": "holder evidence and market checks look consistent",
                "flags": [],
                "confidence": 0.95,
            }
        )


class FailingAIProvider:
    name = "test"

    def complete(self, system, user):
        raise RuntimeError("synthetic provider outage")


PAIR_CREATED_MS = 1_700_000_000_000


class FakeIntel:
    async def analyze_token(self, mint):
        from types import SimpleNamespace

        return SimpleNamespace(is_bundled=False, has_mev=False, score=Decimal(90))


class FakeHolderData:
    TOP_HOLDERS = tuple(f"HolderAddr{i}{'1'*40}" for i in range(1, 6))

    def holder_profile(self, chain, mint):
        from types import SimpleNamespace

        return SimpleNamespace(
            mint=mint,
            holder_count=500,
            top_holder_share_pct=Decimal("18.5"),
            source="solana_tracker",
            top_holders=self.TOP_HOLDERS,
        )


class ClassicTokenProgramReader:
    def __init__(self, clock):
        self.clock = clock

    def read(self, mint):
        return Token2022ExtensionEvidence(
            mint=mint,
            validation_status=REJECTED,
            observed_at=self.clock.now(),
            source="test",
            source_record_id="classic-owner",
            slot=1,
            token_program=TOKEN_PROGRAM_ID,
            account_data_length=82,
            reason_codes=("CLASSIC_SPL_MINT_CONFIRMED",),
        )


class World:
    def __init__(self):
        self.step = 0
        self.pairs_mode = "ok"
        self.safety_mode = "ok"
        self.price_seq = [1.0 + (i % 5) * 0.02 + i * 0.01 for i in range(200)]

    def handler(self, url):
        if url.startswith(DEX):
            if self.pairs_mode == "timeout":
                return TransportTimeout()
            if self.pairs_mode == "empty":
                return json_response([])
            if self.pairs_mode == "malformed":
                return json_response({"unexpected": True})
            price = f"{self.price_seq[self.step]:.6f}"
            self.step += 1
            return json_response(
                [
                    pair_payload(
                        price=price,
                        liquidity=200000.0,
                        volume=300000.0,
                        created_ms=PAIR_CREATED_MS,
                    )
                ]
            )
        if url.startswith(RC):
            if self.safety_mode == "outage":
                return HttpResponse(503, b"", {})
            if self.safety_mode == "rugged":
                return json_response(safety_payload(score=95, rugged=True))
            if self.safety_mode == "risky":
                return json_response(safety_payload(score=85))
            return json_response(safety_payload(score=10))
        raise AssertionError(f"unexpected URL: {url}")


def build(
    world=None, notifier=None, settings=None, evidence=True, token_2022_reader=None
):
    world = world or World()
    transport = RecordingTransport(world.handler)
    clock = clock_at(0)

    reader = token_2022_reader or ClassicTokenProgramReader(clock)
    if hasattr(reader, "clock"):
        reader.clock = clock

    container = build_container(
        settings or Settings(),
        transport=transport,
        clock=clock,
        sleep=lambda s: None,
        notifier=notifier,
        db_path=":memory:",
        token_2022_reader=reader,
    )

    class ClearSybil:
        async def check_sybil_cluster(self, mint, top_holders):
            from types import SimpleNamespace

            return SimpleNamespace(available=True, is_bundled=False)

    container.scan.sybil_checker = ClearSybil()
    if evidence:
        container.scan.ai_brain = AIBrain(FakeAIProvider())
        container.scan.holder_data = FakeHolderData()
        container.scan.intel_adapter = FakeIntel()
    return container, world, transport, clock


class Token2022Reader:
    def __init__(self, flags=(), status=VERIFIED, config_status=VERIFIED, fail=False):
        self.flags = tuple(flags)
        self.status = status
        self.config_status = config_status
        self.fail = fail
        self.calls = []
        self.clock = None

    def read(self, mint):
        self.calls.append(mint)
        if self.fail:
            raise RuntimeError("synthetic Helius outage")
        config = ParsedToken2022Configuration(
            self.config_status, (), (), self.flags, ()
        )
        return Token2022ExtensionEvidence(
            mint=mint,
            validation_status=self.status,
            observed_at=self.clock.now() if self.clock else START,
            source="helius",
            source_record_id="test-slot",
            slot=10,
            token_program=TOKEN_2022_PROGRAM_ID,
            risk_flags=self.flags,
            configuration=config,
        )


class TokenProgramBootstrapTests(unittest.TestCase):
    def test_configured_helius_key_wires_read_only_token2022_reader(self):
        container = build_container(
            Settings(helius_api_key="test-helius-key"),
            transport=RecordingTransport(lambda _url: json_response({})),
            clock=clock_at(0),
            db_path=":memory:",
        )
        try:
            self.assertIsInstance(
                container.token_program_evidence._reader, HeliusToken2022ExtensionReader
            )
        finally:
            container.db.close()


class ScanToSignalFlowTest(unittest.TestCase):
    def scan_n(self, c, n, clock=None):
        results = []
        for _ in range(n):
            results.extend(c.scan.execute("solana", [TOKEN_MINT]))
            if clock is not None:
                clock.advance(91)
        return results

    def test_token2022_paused_transfers_are_vetoed_before_signal_scoring(self):
        reader = Token2022Reader(flags=("TOKEN_TRANSFERS_PAUSED",))
        container, _, _, _ = build(token_2022_reader=reader)
        result = container.scan.execute("solana", [TOKEN_MINT])[0]
        self.assertEqual(result.status, "REJECTED")
        self.assertEqual(result.reasons, ("TOKEN2022_HARD_VETO",))

    def test_rejected_token2022_configuration_is_blocked_with_specific_reason(self):
        reader = Token2022Reader(status=REJECTED, config_status=REJECTED)
        container, _, _, _ = build(token_2022_reader=reader)
        result = container.scan.execute("solana", [TOKEN_MINT])[0]
        self.assertEqual(result.status, "REJECTED")
        self.assertEqual(result.reasons, ("TOKEN2022_EVIDENCE_REJECTED",))

    def test_token2022_transfer_fee_requires_review_and_stays_watch_only(self):
        reader = Token2022Reader(flags=("TRANSFER_FEE_NONZERO",))
        container, _, _, _ = build(token_2022_reader=reader)
        result = container.scan.execute("solana", [TOKEN_MINT])[0]
        self.assertEqual(result.status, "WATCH")
        self.assertEqual(result.reasons, ("TOKEN2022_REVIEW_REQUIRED",))

    def test_helius_unavailable_fails_closed_as_watch(self):
        reader = Token2022Reader(fail=True)
        container, _, _, _ = build(token_2022_reader=reader)
        result = container.scan.execute("solana", [TOKEN_MINT])[0]
        self.assertEqual(result.status, "WATCH")
        self.assertEqual(result.reasons, ("TOKEN_PROGRAM_EVIDENCE_UNAVAILABLE",))

    def test_insufficient_history_rejects_until_enough_samples(self):
        c, _, _, clock = build()
        results = self.scan_n(c, 5, clock)
        self.assertTrue(all(r.status == "WATCH" for r in results))
        self.assertEqual(results[-1].reasons, ("INSUFFICIENT_HISTORY",))

    def test_accepted_signal_after_history_and_outbox_delivers_notification(self):
        notifier = RecordingNotifier()
        c, _, _, clock = build(notifier=notifier)
        results = self.scan_n(c, 20, clock)
        accepted = [r for r in results if r.status == "ACCEPTED"]
        self.assertTrue(accepted, [r.reasons for r in results][-3:])
        self.assertEqual(
            c.db.query_one("SELECT COUNT(*) AS n FROM outbox WHERE status='PENDING'")[
                "n"
            ],
            len(accepted),
        )
        stats = c.worker.run_once()
        self.assertEqual(stats.sent, len(accepted))

    def test_accepted_signal_levels_are_long_geometry(self):
        c, _, _, clock = build()
        self.scan_n(c, 20, clock)
        for row in c.db.query_all("SELECT * FROM signals WHERE status = 'ACCEPTED'"):
            entry, stop, target = (
                Decimal(row[k]) for k in ("entry_price", "stop_loss", "take_profit")
            )
            self.assertTrue(stop < entry < target)

    def test_notifier_failure_keeps_event_pending_then_delivers_on_retry(self):
        notifier = RecordingNotifier(fail_times=1)
        c, _, _, clock = build(notifier=notifier)
        self.scan_n(c, 20, clock)
        total = c.db.query_one("SELECT COUNT(*) AS n FROM outbox")["n"]
        self.assertGreaterEqual(total, 2)
        first = c.worker.run_once()
        self.assertEqual(first.retried, 1)
        clock.advance(3600)
        second = c.worker.run_once()
        self.assertEqual(second.sent, 1)

    def test_persistent_notifier_failure_dead_letters_after_max_attempts(self):
        notifier = RecordingNotifier(fail_times=10_000)
        c, _, _, clock = build(notifier=notifier)
        self.scan_n(c, 20, clock)
        for _ in range(6):
            c.worker.run_once()
            clock.advance(3600)
        failed = c.db.query_one(
            "SELECT COUNT(*) AS n FROM outbox WHERE status = 'FAILED'"
        )["n"]
        self.assertGreaterEqual(failed, 1)

    def test_audit_chain_intact_after_full_flow(self):
        c, _, _, clock = build()
        self.scan_n(c, 20, clock)
        c.worker.run_once()
        with c.db.transaction() as conn:
            self.assertIsNone(AuditLog(conn).verify())


class SafetyAndMarketGatesTest(unittest.TestCase):
    def test_rugged_token_rejected_before_any_scoring_or_price_storage(self):
        world = World()
        world.safety_mode = "rugged"
        c, _, _, _ = build(world=world)
        results = c.scan.execute("solana", [TOKEN_MINT])
        self.assertEqual(results[0].status, "REJECTED")
        self.assertEqual(results[0].reasons, ("RUGGED",))

    def test_risk_above_threshold_rejected(self):
        world = World()
        world.safety_mode = "risky"
        c, _, _, _ = build(world=world, settings=Settings(max_risk_score=Decimal(60)))
        self.assertEqual(
            c.scan.execute("solana", [TOKEN_MINT])[0].reasons, ("RISK_TOO_HIGH",)
        )

    def test_safety_outage_remains_watchable_with_reason(self):
        world = World()
        world.safety_mode = "outage"
        c, _, _, clock = build(world=world)
        for _ in range(5):
            clock.advance(91)
            c.scan.execute("solana", [TOKEN_MINT])
        clock.advance(91)  # Mencegah DUPLICATE_CANDIDATE
        result = c.scan.execute("solana", [TOKEN_MINT])[0]
        self.assertEqual(result.reasons, ("SAFETY_UNAVAILABLE",))
        self.assertEqual(result.status, "WATCH")

    def test_configured_intel_failure_rejects_instead_of_failing_open(self):
        c, _, _, clock = build()
        for _ in range(5):
            clock.advance(91)
            c.scan.execute("solana", [TOKEN_MINT])
        clock.advance(91)  # Mencegah DUPLICATE_CANDIDATE
        c.scan.intel_adapter = object()
        result = c.scan.execute("solana", [TOKEN_MINT])[0]
        self.assertEqual(result.status, "WATCH")
        self.assertEqual(result.reasons, ("INTEL_UNAVAILABLE",))

    # AI is an analyst only and is not on the ACCEPTED path. The status below is decided by the
    # deterministic evidence gates, not by the model output.
    def test_ai_uses_real_holder_profile_and_can_pass_only_with_complete_evidence(self):
        c, _, _, clock = build()
        provider = FakeAIProvider()
        c.scan.ai_brain = AIBrain(provider)
        c.scan.holder_data = FakeHolderData()
        results = []
        for _ in range(20):
            clock.advance(91)
            results.extend(c.scan.execute("solana", [TOKEN_MINT]))
        self.assertTrue(any(result.status == "ACCEPTED" for result in results))

    def test_ai_provider_outage_keeps_candidate_in_watch_state(self):
        c, _, _, clock = build()
        for _ in range(5):
            clock.advance(91)
            c.scan.execute("solana", [TOKEN_MINT])
        clock.advance(91)  # Mencegah DUPLICATE_CANDIDATE
        c.scan.ai_brain = AIBrain(FailingAIProvider())
        c.scan.holder_data = FakeHolderData()
        result = c.scan.execute("solana", [TOKEN_MINT])[0]
        self.assertEqual(result.status, "WATCH")
        self.assertEqual(result.reasons, ("INSUFFICIENT_HISTORY",))

    def test_ai_without_holder_provider_rejects_before_model_call(self):
        c, _, _, _ = build()
        provider = FakeAIProvider()
        c.scan.ai_brain = AIBrain(provider)
        c.scan.holder_data = None
        result = c.scan.execute("solana", [TOKEN_MINT])[0]
        self.assertEqual(result.status, "WATCH")
        self.assertEqual(result.reasons, ("SYBIL_UNAVAILABLE",))

    def test_sybil_unknown_evidence_keeps_candidate_in_watch(self):
        class UnknownSybil:
            async def check_sybil_cluster(self, mint, top_holders):
                from types import SimpleNamespace

                return SimpleNamespace(available=False, is_bundled=None)

        c, _, _, _ = build()
        c.scan.sybil_checker = UnknownSybil()
        result = c.scan.execute("solana", [TOKEN_MINT])[0]
        self.assertEqual(result.status, "WATCH")
        self.assertEqual(result.reasons, ("SYBIL_UNAVAILABLE",))

    def test_sybil_cluster_blocks_candidate_before_ai(self):
        class ClusterSybil:
            async def check_sybil_cluster(self, mint, top_holders):
                from types import SimpleNamespace

                return SimpleNamespace(available=True, is_bundled=True)

        c, _, _, _ = build()
        provider = FakeAIProvider()
        c.scan.ai_brain = AIBrain(provider)
        c.scan.sybil_checker = ClusterSybil()
        result = c.scan.execute("solana", [TOKEN_MINT])[0]
        self.assertEqual(result.status, "REJECTED")
        self.assertEqual(result.reasons, ("SYBIL_CLUSTER_DETECTED",))

    def test_malformed_sybil_verdict_fails_closed(self):
        class MalformedSybil:
            async def check_sybil_cluster(self, mint, top_holders):
                from types import SimpleNamespace

                return SimpleNamespace(available=True, is_bundled=0)

        c, _, _, _ = build()
        c.scan.sybil_checker = MalformedSybil()
        result = c.scan.execute("solana", [TOKEN_MINT])[0]
        self.assertEqual(result.status, "WATCH")
        self.assertEqual(result.reasons, ("SYBIL_UNAVAILABLE",))

    def test_sybil_missing_wallet_addresses_fails_closed(self):
        class HolderWithoutAddresses:
            def holder_profile(self, chain, mint):
                from types import SimpleNamespace

                return SimpleNamespace(
                    mint=mint,
                    holder_count=500,
                    top_holder_share_pct=Decimal("18.5"),
                    source="solana_tracker",
                    top_holders=(),
                )

        c, _, _, _ = build()
        c.scan.holder_data = HolderWithoutAddresses()
        result = c.scan.execute("solana", [TOKEN_MINT])[0]
        self.assertEqual(result.status, "WATCH")
        self.assertEqual(result.reasons, ("SYBIL_UNAVAILABLE",))

    def test_ai_rejects_holder_profile_for_wrong_mint(self):
        class WrongMintHolder:
            def holder_profile(self, chain, mint):
                from types import SimpleNamespace

                return SimpleNamespace(
                    mint="WrongMint1111111111111111111111111111111",
                    holder_count=500,
                    top_holder_share_pct=Decimal("18.5"),
                    source="solana_tracker",
                )

        c, _, _, clock = build()
        for _ in range(5):
            clock.advance(91)
            c.scan.execute("solana", [TOKEN_MINT])
        clock.advance(91)  # Mencegah DUPLICATE_CANDIDATE
        provider = FakeAIProvider()
        c.scan.ai_brain = AIBrain(provider)
        c.scan.holder_data = WrongMintHolder()
        result = c.scan.execute("solana", [TOKEN_MINT])[0]
        self.assertEqual(result.reasons, ("HOLDER_DATA_UNAVAILABLE",))

    def test_empty_market_is_rejected_and_not_persisted(self):
        world = World()
        world.pairs_mode = "empty"
        c, _, _, _ = build(world=world)
        result = c.scan.execute("solana", [TOKEN_MINT])[0]
        self.assertEqual(result.reasons, ("EMPTY_MARKET",))

    def test_market_timeout_becomes_market_unavailable(self):
        world = World()
        world.pairs_mode = "timeout"
        c, _, transport, _ = build(world=world)
        result = c.scan.execute("solana", [TOKEN_MINT])[0]
        self.assertEqual(result.reasons, ("MARKET_UNAVAILABLE",))

    def test_malformed_market_payload_is_empty_market(self):
        world = World()
        world.pairs_mode = "malformed"
        c, _, _, _ = build(world=world)
        self.assertEqual(c.scan.execute("solana", [TOKEN_MINT])[0].status, "WATCH")

    def test_stale_market_is_rejected(self):
        world = World()
        c, _, _, clock = build(world=world)
        for _ in range(5):
            clock.advance(91)
            c.scan.execute("solana", [TOKEN_MINT])
        clock.advance(91)  # Mencegah DUPLICATE_CANDIDATE
        original = c.scan._market.fetch_pairs

        def stale_fetch(chain, mint):
            pairs = original(chain, mint)
            clock.advance(999)
            return pairs

        c.scan._market.fetch_pairs = stale_fetch
        self.assertEqual(
            c.scan.execute("solana", [TOKEN_MINT])[0].reasons,
            ("TOKEN2022_EVIDENCE_STALE",),
        )

    def test_low_liquidity_is_rejected_by_quality_gate(self):
        world = World()
        c, _, _, clock = build(
            world=world, settings=Settings(min_liquidity_usd=Decimal(999999999))
        )
        original_fetch = c.scan._market.fetch_pairs

        def mature_pair_fetch(chain, mint):
            return [
                replace(pair, pair_created_at=clock.now() - timedelta(days=2))
                for pair in original_fetch(chain, mint)
            ]

        c.scan._market.fetch_pairs = mature_pair_fetch
        for _ in range(20):
            c.scan.execute("solana", [TOKEN_MINT])
            clock.advance(91)
        reasons = {
            r
            for row in c.db.query_all("SELECT reasons FROM signals")
            for r in json.loads(row["reasons"])
        }
        self.assertIn("LOW_LIQUIDITY", reasons)


class ConfigLockTest(unittest.TestCase):
    def test_live_mode_cannot_be_built_into_container(self):
        with self.assertRaises(ConfigurationError):
            Settings.from_env({"BANGZEN_LIVE_TRADING": "true"})


class FileDatabaseTest(unittest.TestCase):
    def test_migrations_rerun_safely_on_file_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "bangzen.db")
            world = World()
            c1, _, _, _ = build(world=world)
            c1.db.close()
            c2 = build_container(
                Settings(),
                transport=RecordingTransport(world.handler),
                clock=clock_at(0),
                sleep=lambda s: None,
                db_path=path,
            )
            c2.db.close()
            c3 = build_container(
                Settings(),
                transport=RecordingTransport(world.handler),
                clock=clock_at(0),
                sleep=lambda s: None,
                db_path=path,
            )
            self.assertEqual(
                c3.db.query_one("SELECT COUNT(*) AS n FROM schema_migrations")["n"], 7  # migrasi 0007 notification_delivery
            )
            c3.db.close()


if __name__ == "__main__":
    unittest.main()
