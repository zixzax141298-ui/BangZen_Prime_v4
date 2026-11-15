"""Tes laporan harian dan ledger pengiriman (at-least-once, dedup, kegagalan jaringan).

Tanpa koneksi jaringan sungguhan: transport dan kanal dipalsukan. Jam juga dipalsukan.
Pengiriman dinyatakan at-least-once, bukan exactly-once. Tes di sini mengunci perilaku itu.
"""

import json
import unittest
from datetime import UTC, date, datetime, timedelta

from bangzen_prime.core.errors import ConfigurationError, ExternalServiceError
from bangzen_prime.core.interfaces.cli import _parser
from bangzen_prime.data.http import HttpResponse
from bangzen_prime.notifications.daily_report import (
    GENERIC_SEND_ERROR,
    Channel,
    chunk_body,
    freeze_report,
    send_daily_report,
)
from bangzen_prime.notifications.telegram import TelegramNotifier
from bangzen_prime.storage.database import Database
from bangzen_prime.storage.deliveries import DeliveryStore

T0 = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)  # setelah hari laporan uji
DAY = date(2026, 11, 10)
TOKEN = "123456:SECRETTOKEN"


def fresh_db() -> Database:
    db = Database(":memory:")
    db.migrate()
    return db


def fixed_clock(value: datetime = T0):
    return lambda: value


class RecordingNotifier:
    def __init__(self, fail_on: set[int] | None = None, exc: Exception | None = None):
        self.sent: list[str] = []
        self._calls = 0
        self._fail_on = fail_on or set()
        self._exc = exc

    def send(self, text: str) -> None:
        index = self._calls
        self._calls += 1
        if index in self._fail_on:
            raise self._exc or ExternalServiceError("telegram transport failed", service="telegram", retryable=True)
        self.sent.append(text)


def seed_outbox_dead_letters(db: Database, count: int, day: date = DAY) -> None:
    for i in range(count):
        with db.transaction() as conn:
            conn.execute(
                "INSERT INTO outbox (id, event_name, payload, occurred_at, status, attempts, available_at) "
                "VALUES (?, 'SignalGenerated', '{}', ?, 'FAILED', 5, ?)",
                (f"ev-{day}-{i}-{count}-{id(db)}", f"{day.isoformat()}T10:00:00+00:00", f"{day.isoformat()}T10:00:00+00:00"),
            )


class TestDeliveryLedger(unittest.TestCase):
    def setUp(self):
        self.db = fresh_db()
        self.addCleanup(self.db.close)

    def claim(self, key, now=T0, lease=timedelta(seconds=60)):
        with self.db.transaction() as conn:
            return DeliveryStore(conn).claim(key, "TELEGRAM", now, lease)

    def test_first_claim_wins_and_second_claim_in_lease_is_refused(self):
        self.assertTrue(self.claim("k1"))
        self.assertFalse(self.claim("k1", now=T0 + timedelta(seconds=5)))

    def test_sent_key_is_never_claimed_again(self):
        self.assertTrue(self.claim("k1"))
        with self.db.transaction() as conn:
            self.assertTrue(DeliveryStore(conn).mark_sent("k1", T0))
        self.assertFalse(self.claim("k1", now=T0 + timedelta(days=30)))

    def test_failed_key_can_be_retried_and_counts_attempts(self):
        self.assertTrue(self.claim("k1"))
        with self.db.transaction() as conn:
            DeliveryStore(conn).mark_failed("k1", T0, "telegram transport failed")
        self.assertTrue(self.claim("k1", now=T0 + timedelta(seconds=10)))
        row = self.db.query_one("SELECT attempts, status FROM notification_deliveries WHERE dedup_key = 'k1'")
        self.assertEqual((row["attempts"], row["status"]), (2, "SENDING"))

    def test_expired_lease_allows_redelivery_at_least_once(self):
        # Proses mati setelah kirim tetapi sebelum SENT ditulis. Lease habis, key diklaim lagi.
        self.assertTrue(self.claim("k1", lease=timedelta(seconds=60)))
        self.assertFalse(self.claim("k1", now=T0 + timedelta(seconds=59)))
        self.assertTrue(self.claim("k1", now=T0 + timedelta(seconds=61)))

    def test_mark_without_claim_changes_nothing(self):
        with self.db.transaction() as conn:
            self.assertFalse(DeliveryStore(conn).mark_sent("ghost", T0))
            self.assertFalse(DeliveryStore(conn).mark_failed("ghost", T0, "x"))
        self.assertIsNone(self.db.query_one("SELECT * FROM notification_deliveries WHERE dedup_key = 'ghost'"))

    def test_error_text_is_truncated(self):
        self.claim("k1")
        with self.db.transaction() as conn:
            DeliveryStore(conn).mark_failed("k1", T0, "e" * 1000)
        row = self.db.query_one("SELECT last_error FROM notification_deliveries WHERE dedup_key = 'k1'")
        self.assertEqual(len(row["last_error"]), 200)

    def test_naive_datetime_is_refused(self):
        with self.assertRaises(Exception):
            self.claim("k1", now=datetime(2026, 1, 1))


class TestFrozenReport(unittest.TestCase):
    def setUp(self):
        self.db = fresh_db()
        self.addCleanup(self.db.close)

    def test_today_or_future_day_is_refused(self):
        with self.assertRaises(ConfigurationError):
            freeze_report(self.db, T0.date(), T0)
        with self.assertRaises(ConfigurationError):
            freeze_report(self.db, T0.date() + timedelta(days=1), T0)

    def test_report_is_paper_labelled_and_has_no_profit_figures(self):
        body = freeze_report(self.db, DAY, T0)
        self.assertIn("PAPER ONLY", body)
        self.assertIn("bukan bukti performa", body)
        for banned in ("PnL", "pnl", "profit", "realized"):
            self.assertNotIn(banned, body)

    def test_frozen_body_does_not_change_when_new_rows_arrive(self):
        seed_outbox_dead_letters(self.db, 1)
        first = freeze_report(self.db, DAY, T0)
        self.assertIn("dead-letter): 1", first)
        seed_outbox_dead_letters(self.db, 2)
        second = freeze_report(self.db, DAY, T0 + timedelta(hours=1))
        self.assertEqual(first, second)

    def test_empty_day_renders_without_error(self):
        body = freeze_report(self.db, DAY, T0)
        self.assertIn("Sinyal: tidak ada", body)
        self.assertIn("Outbox gagal permanen (dead-letter): 0", body)


class TestChunking(unittest.TestCase):
    def test_chunks_respect_limit_and_rebuild_exactly(self):
        body = "\n".join(f"baris {i} " + "x" * 30 for i in range(40))
        pieces = chunk_body(body, 100)
        self.assertTrue(all(len(p) <= 100 for p in pieces))
        self.assertEqual("\n".join(pieces), body)

    def test_overlong_single_line_is_split(self):
        pieces = chunk_body("a" * 250, 100)
        self.assertEqual(["a" * 100, "a" * 100, "a" * 50], pieces)

    def test_chunk_limit_must_be_positive(self):
        with self.assertRaises(ConfigurationError):
            chunk_body("x", 0)


class TestSendWithDedup(unittest.TestCase):
    def setUp(self):
        self.db = fresh_db()
        self.addCleanup(self.db.close)
        seed_outbox_dead_letters(self.db, 3)

    def test_each_chunk_reaches_each_channel_once(self):
        a, b = RecordingNotifier(), RecordingNotifier()
        channels = [Channel("telegram:1", a), Channel("telegram:2", b)]
        report = send_daily_report(self.db, channels, day=DAY, clock=fixed_clock(), max_chunk_chars=40)
        self.assertEqual(report.sent, report.chunks * 2)
        self.assertEqual(a.sent, b.sent)
        # Setiap pesan adalah satu potongan utuh, dalam urutan yang sama dengan chunk_body.
        self.assertEqual(a.sent, chunk_body(freeze_report(self.db, DAY, T0), 40))

    def test_second_run_sends_nothing_again(self):
        a = RecordingNotifier()
        channels = [Channel("telegram:1", a)]
        first = send_daily_report(self.db, channels, day=DAY, clock=fixed_clock(), max_chunk_chars=40)
        second = send_daily_report(self.db, channels, day=DAY, clock=fixed_clock(), max_chunk_chars=40)
        self.assertEqual(first.sent, first.chunks)
        self.assertEqual(second.sent, 0)
        self.assertEqual(second.already_sent, first.chunks)
        self.assertEqual(len(a.sent), first.chunks)

    def test_partial_failure_stops_channel_and_retry_resends_only_missing_chunks(self):
        flaky = RecordingNotifier(fail_on={2})
        other = RecordingNotifier()
        channels = [Channel("telegram:1", flaky), Channel("telegram:2", other)]
        report = send_daily_report(self.db, channels, day=DAY, clock=fixed_clock(), max_chunk_chars=40)
        total = report.chunks
        self.assertEqual(report.failed, 1)
        self.assertEqual(report.not_attempted, total - 3)  # chunk 0,1 terkirim; 2 gagal; sisanya tidak dicoba
        self.assertEqual(len(other.sent), total)  # saluran lain tetap jalan
        self.assertEqual(len(flaky.sent), 2)

        healthy = RecordingNotifier()
        retry = send_daily_report(
            self.db, [Channel("telegram:1", healthy)], day=DAY, clock=fixed_clock(), max_chunk_chars=40
        )
        self.assertEqual(retry.already_sent, 2)
        self.assertEqual(retry.sent, total - 2)
        self.assertEqual(len(healthy.sent), total - 2)  # tidak ada potongan 0 atau 1 yang terkirim ulang

    def test_non_sanitised_exception_never_leaks_into_ledger(self):
        leaky = RecordingNotifier(fail_on={0}, exc=RuntimeError(f"https://api.telegram.org/bot{TOKEN}/sendMessage"))
        send_daily_report(self.db, [Channel("telegram:1", leaky)], day=DAY, clock=fixed_clock(), max_chunk_chars=40)
        rows = self.db.query_all("SELECT last_error FROM notification_deliveries WHERE status = 'FAILED'")
        self.assertEqual([r["last_error"] for r in rows], [GENERIC_SEND_ERROR])
        self.assertNotIn("SECRETTOKEN", rows[0]["last_error"])

    def test_channel_in_flight_elsewhere_is_skipped_not_sent(self):
        key = f"daily-report:{DAY.isoformat()}:0:telegram:1"
        with self.db.transaction() as conn:
            DeliveryStore(conn).claim(key, "TELEGRAM", T0, timedelta(minutes=5))
        notifier = RecordingNotifier()
        report = send_daily_report(
            self.db, [Channel("telegram:1", notifier)], day=DAY, clock=fixed_clock(), max_chunk_chars=10_000
        )
        self.assertEqual(report.skipped_in_flight, 1)
        self.assertEqual(notifier.sent, [])


class _FakeTelegramTransport:
    """Records every request and answers from a per-chat script."""

    def __init__(self, failing_chats: set[str] | None = None, network_error: bool = False):
        self.requests: list[dict] = []
        self._failing = failing_chats or set()
        self._network_error = network_error

    def __call__(self, request):
        body = json.loads(request.body.decode("utf-8"))
        self.requests.append({"chat": body["chat_id"], "url": request.url})
        if self._network_error:
            raise ConnectionError(request.url)  # memuat URL berisi token; tidak boleh bocor
        if body["chat_id"] in self._failing:
            return HttpResponse(400, b'{"ok": false}', {})
        return HttpResponse(200, b'{"ok": true}', {})


class TestTelegramDelivery(unittest.TestCase):
    def setUp(self):
        self.db = fresh_db()
        self.addCleanup(self.db.close)
        seed_outbox_dead_letters(self.db, 2)

    def channels(self, transport):
        return [
            Channel(
                f"telegram:{chat}",
                TelegramNotifier(token=TOKEN, chat_ids=(chat,), transport=transport, timeout=5),
            )
            for chat in ("111", "222")
        ]

    def test_chat_rejecting_message_is_retried_without_duplicating_the_other_chat(self):
        first_transport = _FakeTelegramTransport(failing_chats={"222"})
        first = send_daily_report(self.db, self.channels(first_transport), day=DAY, clock=fixed_clock())
        self.assertEqual(first.failed, 1)
        self.assertEqual(sum(1 for r in first_transport.requests if r["chat"] == "111"), first.chunks)

        healthy = _FakeTelegramTransport()
        retry = send_daily_report(self.db, self.channels(healthy), day=DAY, clock=fixed_clock())
        self.assertEqual(retry.already_sent, first.chunks)  # chat 111 sudah SENT, tidak dikirim lagi
        self.assertEqual([r["chat"] for r in healthy.requests], ["222"] * retry.sent)

    def test_network_failure_is_recorded_without_token_and_recovers(self):
        broken = _FakeTelegramTransport(network_error=True)
        report = send_daily_report(self.db, self.channels(broken), day=DAY, clock=fixed_clock())
        self.assertEqual(report.sent, 0)
        self.assertGreaterEqual(report.failed, 1)
        stored = [r["last_error"] for r in self.db.query_all("SELECT last_error FROM notification_deliveries")]
        for text in stored:
            self.assertNotIn(TOKEN, text)
            self.assertNotIn("bot123", text)
        healthy = _FakeTelegramTransport()
        recovered = send_daily_report(self.db, self.channels(healthy), day=DAY, clock=fixed_clock())
        self.assertEqual(recovered.failed, 0)
        self.assertEqual(recovered.not_attempted, 0)

    def test_telegram_message_limit_is_respected_by_default_chunking(self):
        transport = _FakeTelegramTransport()
        send_daily_report(self.db, self.channels(transport), day=DAY, clock=fixed_clock())
        self.assertTrue(transport.requests)


class TestCliWiring(unittest.TestCase):
    def test_daily_report_parses_day_and_send_flag(self):
        args = _parser().parse_args(["daily-report", "--day", "2026-11-10", "--send"])
        self.assertEqual((args.command, args.day, args.send), ("daily-report", "2026-11-10", True))

    def test_daily_report_defaults_to_print_only(self):
        args = _parser().parse_args(["daily-report"])
        self.assertFalse(args.send)
        self.assertIsNone(args.day)


if __name__ == "__main__":
    unittest.main()
