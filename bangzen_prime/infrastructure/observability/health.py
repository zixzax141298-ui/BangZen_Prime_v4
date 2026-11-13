"""Health report: database reachability, outbox backlog, audit integrity, safety flags."""

from __future__ import annotations

import sqlite3

from bangzen_prime.errors import PersistenceError
from bangzen_prime.infrastructure.persistence.sqlite.database import Database
from bangzen_prime.infrastructure.persistence.sqlite.outbox import AuditLog
from bangzen_prime.settings import Settings


def health_report(db: Database, settings: Settings) -> dict:
    report: dict = {
        "live_trading": settings.live_trading,
        "paper_trading": settings.paper_trading,
        "dry_run": settings.dry_run,
        "broadcast_enabled": settings.broadcast_enabled,
        "emergency_stop": settings.emergency_stop,
    }
    try:
        db.query_one("SELECT 1")
        report["database"] = "OK"
    except (sqlite3.Error, PersistenceError):
        report["database"] = "UNAVAILABLE"
        report["status"] = "DOWN"
        return report
    counts = {r["status"]: r["n"] for r in db.query_all(
        "SELECT status, COUNT(*) AS n FROM outbox GROUP BY status")}
    report["outbox"] = {s: counts.get(s, 0) for s in ("PENDING", "PROCESSING", "SENT", "FAILED")}
    report["open_orders"] = db.query_one(
        "SELECT COUNT(*) AS n FROM orders WHERE status IN ('FILLED', 'PARTIALLY_FILLED')")["n"]
    with db.transaction() as conn:
        broken = AuditLog(conn).verify()
    report["audit_intact"] = broken is None
    degraded = broken is not None or report["outbox"]["FAILED"] > 0
    report["status"] = "DEGRADED" if degraded else "OK"
    return report
