"""BANGZEN PRIME — luxury live command deck (rich + pyfiglet).

Paper / signal research view. Does not enable live trading or broadcast.
Optional deps: pip install 'bangzen-prime[dashboard]'
"""

from __future__ import annotations

import os
import sqlite3
import time
from datetime import UTC, datetime

from dotenv import load_dotenv

from bangzen_prime import __version__
from bangzen_prime.core.interfaces.banner import (
    CRIMSON,
    CYAN,
    EMERALD,
    GOLD,
    GOLD_DIM,
    IVORY,
    MUTED,
    VIOLET,
    render_banner,
    render_compact_header,
)

try:
    from rich import box
    from rich.align import Align
    from rich.console import Console, Group
    from rich.layout import Layout
    from rich.live import Live
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "dashboard requires: pip install 'bangzen-prime[dashboard]'"
    ) from exc

load_dotenv()
console = Console()
DB_PATH = os.getenv("BANGZEN_DB_PATH", "bangzen.db")


def _conn() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def _safe_query(sql: str, args: tuple = (), limit: int = 8) -> list[tuple]:
    try:
        with _conn() as conn:
            cur = conn.execute(sql, args)
            return cur.fetchmany(limit)
    except Exception:
        return []


def _mode_label() -> str:
    try:
        from bangzen_prime.core.config import Settings

        return Settings.from_env().operating_mode.value
    except Exception:
        return os.getenv("BANGZEN_OPERATING_MODE", "TELEGRAM_ONLY")


def make_status_strip() -> Panel:
    mode = _mode_label()
    grid = Table.grid(expand=True, padding=(0, 3))
    grid.add_column(justify="center")
    grid.add_column(justify="center")
    grid.add_column(justify="center")
    grid.add_column(justify="center")
    grid.add_row(
        Text.from_markup(f"[{EMERALD}]● PAPER[/]"),
        Text.from_markup(f"[{CYAN}]MODE {mode}[/]"),
        Text.from_markup(f"[{GOLD}]● LIVE LOCKED[/]"),
        Text.from_markup(f"[{MUTED}]UTC {datetime.now(UTC).strftime('%H:%M:%S')}[/]"),
    )
    return Panel(grid, border_style=GOLD_DIM, box=box.ROUNDED, height=3)


def make_radar_panel() -> Panel:
    rows = _safe_query("SELECT mint, symbol FROM tokens ORDER BY rowid DESC LIMIT 10")
    table = Table(
        expand=True,
        box=box.SIMPLE_HEAVY,
        show_header=True,
        header_style=f"bold {GOLD}",
        border_style=MUTED,
    )
    table.add_column("#", style=MUTED, width=3)
    table.add_column("MINT", style=CYAN, overflow="ellipsis")
    table.add_column("SYMBOL", style=IVORY)

    if not rows:
        table.add_row("—", "awaiting discoveries…", "—")
    else:
        for i, (mint, symbol) in enumerate(rows, 1):
            short = (
                f"{mint[:4]}…{mint[-4:]}" if mint and len(mint) > 12 else (mint or "—")
            )
            table.add_row(str(i), short, symbol or "—")

    return Panel(
        table,
        title=f"[bold {IVORY}] RADAR · RECENT TOKENS [/]",
        border_style=CYAN,
        box=box.HEAVY,
    )


def make_signals_panel() -> Panel:
    rows = _safe_query(
        "SELECT id, status, score FROM signals ORDER BY rowid DESC LIMIT 8"
    )
    table = Table(expand=True, box=box.SIMPLE, header_style=f"bold {GOLD}")
    table.add_column("REF", style=MUTED, max_width=10)
    table.add_column("STATUS", style=IVORY)
    table.add_column("SCORE", justify="right", style=CYAN)

    if not rows:
        table.add_row("—", "no signals yet", "—")
    else:
        for sid, status, score in rows:
            ref = str(sid)[:8] if sid else "—"
            st = str(status or "—")
            style = (
                EMERALD
                if "ACCEPT" in st.upper()
                else (CRIMSON if "REJECT" in st.upper() else IVORY)
            )
            table.add_row(
                ref, Text(st, style=style), str(score if score is not None else "—")
            )

    return Panel(
        table,
        title=f"[bold {IVORY}] SIGNALS [/]",
        border_style=VIOLET,
        box=box.HEAVY,
    )


def make_portfolio_panel() -> Panel:
    open_rows = _safe_query(
        "SELECT status, COUNT(*) FROM orders GROUP BY status LIMIT 12"
    )
    table = Table(expand=True, box=box.SIMPLE, header_style=f"bold {GOLD}")
    table.add_column("STATUS", style=IVORY)
    table.add_column("COUNT", justify="right", style=CYAN)

    if not open_rows:
        table.add_row("paper book", "empty")
    else:
        for status, cnt in open_rows:
            table.add_row(str(status), str(cnt))

    return Panel(
        table,
        title=f"[bold {IVORY}] PAPER BOOK [/]",
        border_style=EMERALD,
        box=box.HEAVY,
    )


def make_security_panel() -> Panel:
    lines = Table.grid(padding=(0, 1))
    lines.add_column(style=MUTED, width=16)
    lines.add_column(style=IVORY)
    lines.add_row("Live trading", Text("DISABLED", style=f"bold {EMERALD}"))
    lines.add_row("Broadcast", Text("REFUSED", style=f"bold {EMERALD}"))
    lines.add_row("Signer", Text("LOCKED", style=f"bold {GOLD}"))
    lines.add_row("Burner key", Text("REMOVED", style=MUTED))
    lines.add_row("Default path", "paper + signal only")
    return Panel(
        lines,
        title=f"[bold {IVORY}] SECURITY POSTURE [/]",
        border_style=GOLD,
        box=box.HEAVY,
    )


def make_footer() -> Panel:
    t = Text(justify="center")
    t.append("BANGZEN PRIME", style=f"bold {GOLD}")
    t.append("  ·  ", style=MUTED)
    t.append("CTRL+C EXIT", style=MUTED)
    t.append("  ·  ", style=MUTED)
    t.append("NO LIVE BROADCAST", style=EMERALD)
    return Panel(t, border_style=GOLD_DIM, box=box.ROUNDED, height=3)


def build_dashboard() -> Layout:
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=8),
        Layout(name="strip", size=3),
        Layout(name="body", ratio=1),
        Layout(name="footer", size=3),
    )
    layout["header"].update(
        render_compact_header(version=__version__, mode=_mode_label())
    )
    layout["strip"].update(make_status_strip())
    layout["footer"].update(make_footer())

    layout["body"].split_row(
        Layout(name="left", ratio=3),
        Layout(name="right", ratio=2),
    )
    layout["left"].update(make_radar_panel())
    layout["right"].split_column(
        Layout(make_signals_panel(), ratio=2),
        Layout(make_portfolio_panel(), ratio=1),
        Layout(make_security_panel(), ratio=1),
    )
    return layout


def splash() -> None:
    """One-shot luxury splash before the live deck."""
    console.clear()
    render_banner(
        console=console,
        version=__version__,
        mode=_mode_label(),
        paper=True,
        live_locked=True,
        subtitle="Command deck · research only",
    )
    console.print()
    console.print(Align.center(Text("initializing command deck…", style=MUTED)))
    time.sleep(0.8)


def main() -> None:
    splash()
    try:
        with Live(
            build_dashboard(), console=console, screen=True, refresh_per_second=1
        ) as live:
            while True:
                live.update(build_dashboard())
                time.sleep(1)
    except KeyboardInterrupt:
        pass
    console.print()
    console.print(
        Panel(
            Align.center(Text("SESSION CLOSED · STAY SAFE", style=f"bold {GOLD}")),
            border_style=GOLD,
            box=box.DOUBLE_EDGE,
        )
    )


if __name__ == "__main__":
    main()
