"""Laporan harian paper. Isinya ringkasan operasional, bukan sinyal beli atau jual,
dan BUKAN bukti performa. Laporan ini tidak memuat angka profit atau PnL.

Alur:
1. Laporan untuk satu hari UTC yang sudah selesai dibekukan di tabel daily_reports (tulis sekali).
2. Isi dipotong ke batas Telegram. Setiap pasangan (potongan, saluran) punya dedup key sendiri.
3. Sebelum mengirim, klaim key di notification_deliveries. Key yang sudah SENT dilewati.
4. Jika satu potongan gagal pada sebuah saluran, saluran itu berhenti agar urutan terjaga.
   Saluran lain tetap jalan. Pemanggilan berikutnya hanya mengirim potongan yang belum SENT.

Semantik pengiriman: at-least-once. Duplikat bisa terjadi jika proses berhenti tepat setelah
kanal menerima pesan dan sebelum status SENT ditulis. Exactly-once tidak diklaim.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Protocol

from bangzen_prime.core.errors import ConfigurationError, ExternalServiceError
from bangzen_prime.storage.database import Database, utc_iso
from bangzen_prime.storage.deliveries import DeliveryStore

MAX_CHUNK_CHARS = 4000  # batas Telegram 4096, dengan margin
DEFAULT_LEASE = timedelta(minutes=2)
CHANNEL_KIND = "TELEGRAM"
GENERIC_SEND_ERROR = "send failed"


class TextSink(Protocol):
    def send(self, text: str) -> None: ...


@dataclass(frozen=True)
class Channel:
    name: str  # id stabil untuk dedup key, misalnya "telegram:<chat_id>"
    notifier: TextSink


@dataclass
class DeliveryReport:
    day: str
    chunks: int
    sent: int = 0
    already_sent: int = 0
    skipped_in_flight: int = 0
    failed: int = 0
    not_attempted: int = 0

    def as_dict(self) -> dict:
        return asdict(self)


def _window(day: date) -> tuple[str, str]:
    start = datetime(day.year, day.month, day.day, tzinfo=UTC)
    return utc_iso(start), utc_iso(start + timedelta(days=1))


def build_body(conn, day: date) -> str:
    start, end = _window(day)
    signals = {
        r["status"]: r["n"]
        for r in conn.execute(
            "SELECT status, COUNT(*) AS n FROM signals "
            "WHERE created_at >= ? AND created_at < ? GROUP BY status",
            (start, end),
        ).fetchall()
    }
    orders = {
        r["status"]: r["n"]
        for r in conn.execute(
            "SELECT status, COUNT(*) AS n FROM orders "
            "WHERE created_at >= ? AND created_at < ? GROUP BY status",
            (start, end),
        ).fetchall()
    }
    phases = conn.execute(
        "SELECT COUNT(*) AS n FROM forward_order_phase WHERE recorded_at >= ? AND recorded_at < ?",
        (start, end),
    ).fetchone()["n"]
    dead = conn.execute(
        "SELECT COUNT(*) AS n FROM outbox WHERE status = 'FAILED' "
        "AND occurred_at >= ? AND occurred_at < ?",
        (start, end),
    ).fetchone()["n"]

    def breakdown(counts: dict) -> str:
        if not counts:
            return "tidak ada"
        return ", ".join(f"{k}: {counts[k]}" for k in sorted(counts))

    lines = [
        f"[LAPORAN HARIAN | PAPER ONLY] {day.isoformat()} (UTC)",
        "Ringkasan operasional. Bukan sinyal beli atau jual dan bukan bukti performa.",
        f"Sinyal: {breakdown(signals)}",
        f"Order paper: {breakdown(orders)}",
        f"Fase posisi paper tercatat: {phases}",
        f"Outbox gagal permanen (dead-letter): {dead}",
    ]
    return "\n".join(lines)


def freeze_report(db: Database, day: date, now: datetime) -> str:
    """Return the frozen report for a finished UTC day, creating it once if needed."""
    if day >= now.astimezone(UTC).date():
        raise ConfigurationError("laporan hanya untuk hari UTC yang sudah selesai")
    key = day.isoformat()
    with db.transaction() as conn:
        row = conn.execute("SELECT body FROM daily_reports WHERE day = ?", (key,)).fetchone()
        if row is None:
            body = build_body(conn, day)
            stamp = utc_iso(now.astimezone(UTC))
            conn.execute(
                "INSERT OR IGNORE INTO daily_reports (day, body, created_at) VALUES (?, ?, ?)",
                (key, body, stamp),
            )
            row = conn.execute("SELECT body FROM daily_reports WHERE day = ?", (key,)).fetchone()
    return row["body"]


def chunk_body(body: str, limit: int = MAX_CHUNK_CHARS) -> list[str]:
    """Split on line boundaries. A single line longer than limit is split hard."""
    if limit < 1:
        raise ConfigurationError("chunk limit must be >= 1")
    pieces: list[str] = []
    current = ""
    for line in body.split("\n"):
        while len(line) > limit:
            if current:
                pieces.append(current)
                current = ""
            pieces.append(line[:limit])
            line = line[limit:]
        candidate = line if not current else f"{current}\n{line}"
        if len(candidate) > limit:
            pieces.append(current)
            current = line
        else:
            current = candidate
    if current or not pieces:
        pieces.append(current)
    return pieces


def send_daily_report(
    db: Database,
    channels: Sequence[Channel],
    *,
    day: date,
    clock: Callable[[], datetime],
    lease: timedelta = DEFAULT_LEASE,
    max_chunk_chars: int = MAX_CHUNK_CHARS,
) -> DeliveryReport:
    body = freeze_report(db, day, clock())
    chunks = chunk_body(body, max_chunk_chars)
    report = DeliveryReport(day=day.isoformat(), chunks=len(chunks))
    total = len(chunks)
    for channel in channels:
        processed = 0
        for index, chunk in enumerate(chunks):
            key = f"daily-report:{day.isoformat()}:{index}:{channel.name}"
            with db.transaction() as conn:
                store = DeliveryStore(conn)
                claimed = store.claim(key, CHANNEL_KIND, clock(), lease)
                if not claimed:
                    status = store.status(key)
            if not claimed:
                if status == "SENT":
                    report.already_sent += 1
                else:
                    report.skipped_in_flight += 1
                processed += 1
                continue
            # Network call happens outside any transaction so no DB lock is held during I/O.
            try:
                channel.notifier.send(chunk)
            except Exception as exc:
                # Only our own sanitised messages are stored. Other exceptions may carry URLs
                # or tokens, so they are replaced with a generic text.
                message = str(exc) if isinstance(exc, ExternalServiceError) else GENERIC_SEND_ERROR
                with db.transaction() as conn:
                    DeliveryStore(conn).mark_failed(key, clock(), message)
                report.failed += 1
                processed += 1
                # Stop this channel so chunks do not arrive out of order. Other channels go on.
                break
            with db.transaction() as conn:
                DeliveryStore(conn).mark_sent(key, clock())
            report.sent += 1
            processed += 1
        report.not_attempted += total - processed
    return report
