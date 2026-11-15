"""Command-line interface. Read-only and paper operations only. There is no live command."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections.abc import Mapping, Sequence

from bangzen_prime import __version__
from bangzen_prime.core.config import Settings, load_settings_env
from bangzen_prime.core.errors import BangzenError, ConfigurationError, HaltEngagedError
from bangzen_prime.core.logging_utils import configure_logging, redact

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
    daily_p = sub.add_parser(
        "daily-report",
        help="Print the frozen UTC daily paper report; --send delivers it via Telegram.",
    )
    daily_p.add_argument("--day", help="YYYY-MM-DD, a finished UTC day. Default: yesterday UTC.")
    daily_p.add_argument("--send", action="store_true", help="Send to the Telegram allowlist.")
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
    forward_p = sub.add_parser(
        "forward-paper",
        help="Forward paper test: scan, open paper orders, record to a frozen ledger (paper only).",
    )
    forward_p.add_argument("--watchlist", required=True, help="File with one mint per line.")
    forward_p.add_argument("--ledger", required=True, help="JSONL ledger path (config frozen on first use).")
    forward_p.add_argument("--interval-seconds", type=int, default=60)
    forward_p.add_argument("--cycles", type=int, default=0, help="0 = run until halted or stopped.")
    forward_p.add_argument("--scans-per-minute", type=int, default=20)
    forward_p.add_argument(
        "--signal-max-age-seconds", type=int, default=300,
        help="Only signals created within this age are executed.",
    )
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


def resolve_env_file(environ: Mapping[str, str]) -> str:
    """BANGZEN_ENV_FILE names the env file. Missing explicit file is an error. Missing default is a warning."""
    explicit = environ.get("BANGZEN_ENV_FILE")
    if explicit is not None:
        if not os.path.isfile(explicit):
            raise ConfigurationError("BANGZEN_ENV_FILE does not point to an existing file")
        return explicit
    return ".env"


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        env_path = resolve_env_file(os.environ)
        if not os.path.isfile(env_path):
            print(
                f"warning: no .env at {os.path.abspath(env_path)}; using environment variables only",
                file=sys.stderr,
            )
        settings = Settings.from_env(load_settings_env(env_path))
    except BangzenError as exc:
        print(f"configuration error: {redact(str(exc))}", file=sys.stderr)
        return EXIT_ERROR
    configure_logging(settings.log_level, sys.stderr)
    try:
        return _dispatch(args, settings)
    except BangzenError as exc:
        print(f"error: {redact(str(exc))}", file=sys.stderr)
        return EXIT_ERROR


def _run_daily_report(args, settings: Settings, container) -> int:
    from datetime import UTC, date, datetime, timedelta

    from bangzen_prime.data.http import urllib_request_transport
    from bangzen_prime.notifications.daily_report import Channel, freeze_report, send_daily_report
    from bangzen_prime.notifications.telegram import TelegramNotifier

    now = datetime.now(UTC)
    day = (
        date.fromisoformat(args.day)
        if args.day
        else (now - timedelta(days=1)).date()
    )
    if not args.send:
        # Local only: freezes the report text and prints it. No network and no delivery ledger.
        print(freeze_report(container.db, day, now))
        return EXIT_OK
    if not container.mode_controller.snapshot().telegram_enabled:
        print("telegram is disabled by the operating mode; nothing sent", file=sys.stderr)
        return EXIT_ERROR
    if not (settings.telegram_bot_token and settings.telegram_allowed_chat_ids):
        print("telegram is not configured; nothing sent", file=sys.stderr)
        return EXIT_ERROR
    channels = [
        Channel(
            name=f"telegram:{chat_id}",
            notifier=TelegramNotifier(
                token=settings.telegram_bot_token,
                chat_ids=(chat_id,),
                transport=urllib_request_transport,
                timeout=settings.http_timeout_seconds,
            ),
        )
        for chat_id in settings.telegram_allowed_chat_ids
    ]
    report = send_daily_report(
        container.db,
        channels,
        day=day,
        clock=lambda: datetime.now(UTC),
    )
    print(json.dumps(report.as_dict()))
    clean = report.failed == 0 and report.not_attempted == 0
    return EXIT_OK if clean else EXIT_ERROR


def _dispatch(args, settings: Settings) -> int:
    if args.command == "status":
        try:
            from bangzen_prime.core.interfaces.banner import render_banner

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
        from bangzen_prime.core.interfaces.demo import run_demo

        print(json.dumps(run_demo(scans=args.scans), indent=2, default=str))
        return EXIT_OK
    if args.command == "soak":
        from bangzen_prime.core.interfaces.soak import run_soak

        report = run_soak(cycles=args.cycles, seed=args.seed)
        print(json.dumps(report, indent=2, default=str))
        return EXIT_OK if report["passed"] else EXIT_ERROR
    if args.command == "restore":
        from bangzen_prime.storage import maintenance

        maintenance.restore(args.path, settings.db_path)
        print(json.dumps({"restored_from": args.path, "into": settings.db_path}))
        return EXIT_OK
    if args.command == "forward-paper":
        from bangzen_prime.core.forward_runner import ForwardRunSettings

        try:
            run_settings = ForwardRunSettings(
                watchlist_path=args.watchlist,
                ledger_path=args.ledger,
                interval_seconds=args.interval_seconds,
                cycles=args.cycles,
                scans_per_minute=args.scans_per_minute,
                signal_max_age_seconds=args.signal_max_age_seconds,
            )
            run_settings.validate()
        except ConfigurationError as exc:
            print(f"forward-paper: {exc}", file=sys.stderr)
            return EXIT_ERROR
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
            from bangzen_prime.core.interfaces.dashboard import main as run_dashboard
        except ImportError as exc:
            print(
                "dashboard needs optional packages: pip install 'bangzen-prime[dashboard]'"
                f" ({exc.name} missing)",
                file=sys.stderr,
            )
            return EXIT_ERROR
        run_dashboard()
        return EXIT_OK

    if args.command in {"scan", "discover", "outbox", "monitor", "forward-paper"} and settings.halt_active():
        print(
            "emergency stop is active (BANGZEN_EMERGENCY_STOP=true or HALT.flag present); "
            f"refusing '{args.command}'",
            file=sys.stderr,
        )
        return EXIT_ERROR
    from bangzen_prime.core.bootstrap import build_container

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
                    except HaltEngagedError:
                        print(
                            "discovery halted: emergency stop engaged",
                            file=sys.stderr,
                            flush=True,
                        )
                        break
                    except BangzenError as exc:
                        print(
                            f"discovery cycle failed; will retry after interval: {redact(str(exc))}",
                            file=sys.stderr,
                            flush=True,
                        )
                    if args.once:
                        break
                    time.sleep(args.interval_seconds)
            except KeyboardInterrupt:
                print("discovery stopped by operator", file=sys.stderr, flush=True)
        elif args.command == "monitor":
            from bangzen_prime.core.monitor import Monitor, load_watchlist
            from bangzen_prime.data.api_budget_defaults import (
                default_budget_registry,
            )

            mints = load_watchlist(args.watchlist)
            budget = default_budget_registry(
                time.monotonic, scans_per_minute=args.scans_per_minute
            )
            monitor = Monitor(
                scan=container.scan,
                worker=container.worker,
                budget=budget,
                watchlist=mints,
                halt_check=settings.halt_active,
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
                                "halted": report.halted,
                                "transitions": [t.__dict__ for t in report.transitions],
                            }
                        ),
                        flush=True,
                    )
            except KeyboardInterrupt:
                print("monitor stopped by operator", file=sys.stderr, flush=True)
        elif args.command == "forward-paper":
            from bangzen_prime.core.forward_runner import run_forward_paper

            try:
                run_forward_paper(container, settings, run_settings)
            except KeyboardInterrupt:
                print("forward-paper stopped by operator", file=sys.stderr, flush=True)
        elif args.command == "daily-report":
            return _run_daily_report(args, settings, container)
        elif args.command == "outbox":
            print(json.dumps(container.worker.run_once().__dict__))
        elif args.command == "health":
            from bangzen_prime.core.observability.health import health_report

            report = health_report(container.db, settings)
            print(json.dumps(report, indent=2))
            return EXIT_OK if report["status"] == "OK" else EXIT_ERROR
        elif args.command == "backup":
            from bangzen_prime.storage import maintenance

            maintenance.backup(container.db, args.path)
            print(json.dumps({"backup_written": args.path}))
        elif args.command == "prune":
            from datetime import UTC, datetime, timedelta

            from bangzen_prime.storage import maintenance

            result = maintenance.prune(
                container.db, now=datetime.now(UTC), retain=timedelta(days=args.days)
            )
            print(json.dumps(result))
        elif args.command == "audit-verify":
            from bangzen_prime.storage.outbox import AuditLog

            with container.db.transaction() as conn:
                broken = AuditLog(conn).verify()
            print(json.dumps({"intact": broken is None, "broken_at_seq": broken}))
            return EXIT_OK if broken is None else EXIT_ERROR
        return EXIT_OK
    finally:
        container.db.close()
