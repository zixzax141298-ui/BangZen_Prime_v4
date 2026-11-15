"""Command-line interface. Read-only and paper operations only. There is no live command."""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Sequence

from bangzen_prime import __version__
from bangzen_prime.errors import BangzenError
from bangzen_prime.logging_utils import configure_logging
from bangzen_prime.settings import Settings, load_settings_env

EXIT_OK = 0
EXIT_ERROR = 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bangzen-prime",
        description="Solana token intelligence. Signal-only and paper modes. Live trading is locked.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="Show effective safety settings (no secrets).")
    sub.add_parser("migrate", help="Apply database migrations (idempotent).")
    scan = sub.add_parser(
        "scan", help="Scan mints using the live market APIs (network)."
    )
    scan.add_argument("mints", nargs="+", help="Base58 Solana token addresses.")
    scan.add_argument("--chain", default="solana")
    discover = sub.add_parser(
        "discover", help="Continuously discover and scan new Solana token candidates."
    )
    discover.add_argument("--interval-seconds", type=int, default=60)
    discover.add_argument("--limit", type=int, default=30)
    discover.add_argument(
        "--once", action="store_true", help="Run one discovery cycle and exit."
    )
    sub.add_parser("dashboard", help="Launch the visual live radar dashboard.")
    sub.add_parser("outbox", help="Run one outbox delivery pass.")
    monitor_p = sub.add_parser(
        "monitor", help="Continuously scan a watchlist (paper only)."
    )
    monitor_p.add_argument(
        "--watchlist", required=True, help="File with one mint per line."
    )
    monitor_p.add_argument("--interval-seconds", type=int, default=60)
    monitor_p.add_argument(
        "--cycles", type=int, default=0, help="0 = run until stopped."
    )
    monitor_p.add_argument("--scans-per-minute", type=int, default=20)
    sub.add_parser("audit-verify", help="Verify the audit hash chain.")
    demo = sub.add_parser("demo", help="Offline deterministic demo (no network).")
    demo.add_argument("--scans", type=int, default=25)
    soak = sub.add_parser(
        "soak", help="Offline seeded paper soak test with invariant checks."
    )
    soak.add_argument("--cycles", type=int, default=200)
    soak.add_argument("--seed", type=int, default=7)
    sub.add_parser("health", help="Print a health report (no secrets).")
    backup_p = sub.add_parser(
        "backup", help="Write a verified-on-restore copy of the database."
    )
    backup_p.add_argument("path")
    restore_p = sub.add_parser(
        "restore", help="Verify a backup and atomically replace the database."
    )
    restore_p.add_argument("path")
    prune_p = sub.add_parser(
        "prune", help="Delete delivered outbox rows older than N days."
    )
    prune_p.add_argument("--days", type=int, default=30)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        settings = Settings.from_env(load_settings_env())
    except BangzenError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    configure_logging(settings.log_level, sys.stderr)
    try:
        return _dispatch(args, settings)
    except BangzenError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR


def _dispatch(args, settings: Settings) -> int:
    if args.command == "status":
        try:
            from bangzen_prime.interfaces.banner import render_banner

            render_banner(
                version=__version__,
                mode=getattr(
                    settings.operating_mode, "value", str(settings.operating_mode)
                ),
                paper=settings.paper_trading,
                live_locked=not settings.live_trading,
            )
        except Exception:
            pass  # nosec B110
        print(
            json.dumps(
                {
                    "version": __version__,
                    "live_trading": settings.live_trading,
                    "paper_trading": settings.paper_trading,
                    "dry_run": settings.dry_run,
                    "emergency_stop": settings.emergency_stop,
                    "operating_mode": getattr(
                        settings.operating_mode, "value", str(settings.operating_mode)
                    ),
                    "db_path": settings.db_path,
                    "telegram_configured": settings.telegram_bot_token is not None,
                },
                indent=2,
            )
        )
        return EXIT_OK
    if args.command == "demo":
        from bangzen_prime.interfaces.demo import run_demo

        print(json.dumps(run_demo(scans=args.scans), indent=2, default=str))
        return EXIT_OK
    if args.command == "soak":
        from bangzen_prime.interfaces.soak import run_soak

        report = run_soak(cycles=args.cycles, seed=args.seed)
        print(json.dumps(report, indent=2, default=str))
        return EXIT_OK if report["passed"] else EXIT_ERROR
    if args.command == "restore":
        from bangzen_prime.infrastructure.persistence.sqlite import maintenance

        maintenance.restore(args.path, settings.db_path)
        print(json.dumps({"restored_from": args.path, "into": settings.db_path}))
        return EXIT_OK
    if args.command == "monitor" and (
        args.interval_seconds < 15 or args.scans_per_minute < 1 or args.cycles < 0
    ):
        print(
            "monitor requires --interval-seconds >= 15, --scans-per-minute >= 1, --cycles >= 0",
            file=sys.stderr,
        )
        return EXIT_ERROR
    if args.command == "discover" and (
        args.interval_seconds < 15 or not 1 <= args.limit <= 100
    ):
        print(
            "discover requires --interval-seconds >= 15 and --limit in [1, 100]",
            file=sys.stderr,
        )
        return EXIT_ERROR

    if args.command == "dashboard":
        try:
            from bangzen_prime.interfaces.dashboard import main as run_dashboard
        except ImportError as exc:
            print(
                "dashboard needs optional packages: pip install 'bangzen-prime[dashboard]'"
                f" ({exc.name} missing)",
                file=sys.stderr,
            )
            return EXIT_ERROR
        run_dashboard()
        return EXIT_OK

    if settings.emergency_stop and args.command in {"scan", "discover", "outbox"}:
        print(
            "emergency stop is active (BANGZEN_EMERGENCY_STOP=true); refusing "
            f"'{args.command}'",
            file=sys.stderr,
        )
        return EXIT_ERROR
    from bangzen_prime.bootstrap import build_container

    container = build_container(settings)
    try:
        if args.command == "migrate":
            versions = [
                r["version"]
                for r in container.db.query_all(
                    "SELECT version FROM schema_migrations ORDER BY version"
                )
            ]
            print(json.dumps({"schema_versions": versions}))
        elif args.command == "scan":
            results = container.scan.execute(args.chain, args.mints)
            print(json.dumps([r.__dict__ for r in results], indent=2))
        elif args.command == "discover":
            try:
                while True:
                    try:
                        cycle = container.discovery.execute(limit=args.limit)
                        print(
                            json.dumps(
                                {
                                    "discovered": cycle.discovered,
                                    "scanned": cycle.scanned,
                                    "skipped_recent": cycle.skipped_recent,
                                    "results": [
                                        result.__dict__ for result in cycle.results
                                    ],
                                },
                                indent=2,
                            ),
                            flush=True,
                        )
                    except BangzenError as exc:
                        print(
                            f"discovery cycle failed; will retry after interval: {exc}",
                            file=sys.stderr,
                            flush=True,
                        )
                    if args.once:
                        break
                    time.sleep(args.interval_seconds)
            except KeyboardInterrupt:
                print("discovery stopped by operator", file=sys.stderr, flush=True)
        elif args.command == "monitor":
            from bangzen_prime.application.api_budget_defaults import (
                default_budget_registry,
            )
            from bangzen_prime.application.monitor import Monitor, load_watchlist

            mints = load_watchlist(args.watchlist)
            budget = default_budget_registry(
                time.monotonic, scans_per_minute=args.scans_per_minute
            )
            monitor = Monitor(
                scan=container.scan,
                worker=container.worker,
                budget=budget,
                watchlist=mints,
            )
            try:
                for report in monitor.run(
                    cycles=args.cycles,
                    interval_seconds=args.interval_seconds,
                    sleep=time.sleep,
                ):
                    print(
                        json.dumps(
                            {
                                "cycle": report.cycle,
                                "scanned": report.scanned,
                                "skipped_budget": report.skipped_budget,
                                "accepted": report.accepted,
                                "transitions": [t.__dict__ for t in report.transitions],
                            }
                        ),
                        flush=True,
                    )
            except KeyboardInterrupt:
                print("monitor stopped by operator", file=sys.stderr, flush=True)
        elif args.command == "outbox":
            print(json.dumps(container.worker.run_once().__dict__))
        elif args.command == "health":
            from bangzen_prime.infrastructure.observability.health import health_report

            report = health_report(container.db, settings)
            print(json.dumps(report, indent=2))
            return EXIT_OK if report["status"] == "OK" else EXIT_ERROR
        elif args.command == "backup":
            from bangzen_prime.infrastructure.persistence.sqlite import maintenance

            maintenance.backup(container.db, args.path)
            print(json.dumps({"backup_written": args.path}))
        elif args.command == "prune":
            from datetime import UTC, datetime, timedelta

            from bangzen_prime.infrastructure.persistence.sqlite import maintenance

            result = maintenance.prune(
                container.db, now=datetime.now(UTC), retain=timedelta(days=args.days)
            )
            print(json.dumps(result))
        elif args.command == "audit-verify":
            from bangzen_prime.infrastructure.persistence.sqlite.outbox import AuditLog

            with container.db.transaction() as conn:
                broken = AuditLog(conn).verify()
            print(json.dumps({"intact": broken is None, "broken_at_seq": broken}))
            return EXIT_OK if broken is None else EXIT_ERROR
        return EXIT_OK
    finally:
        container.db.close()
