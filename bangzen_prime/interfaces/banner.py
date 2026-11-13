"""Luxury terminal banner for BANGZEN PRIME (rich + pyfiglet)."""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from typing import Any

# Optional heavy deps — graceful degrade if missing
try:
    import pyfiglet
except ImportError:  # pragma: no cover
    pyfiglet = None  # type: ignore

try:
    from rich import box
    from rich.align import Align
    from rich.console import Console, Group
    from rich.panel import Panel
    from rich.rule import Rule
    from rich.table import Table
    from rich.text import Text
except ImportError:  # pragma: no cover
    Console = None  # type: ignore


# Palette — noir luxury
GOLD = "#D4AF37"
GOLD_DIM = "#A68B2C"
CYAN = "#5CE1E6"
EMERALD = "#00C853"
CRIMSON = "#FF1744"
VIOLET = "#B388FF"
IVORY = "#F5F0E6"
MUTED = "#6B6560"
OBSIDIAN = "#0D0D0F"


def _figlet(text: str, font: str = "slant") -> str:
    if pyfiglet is None:
        return text
    try:
        return pyfiglet.figlet_format(text, font=font).rstrip()
    except Exception:
        try:
            return pyfiglet.figlet_format(text, font="standard").rstrip()
        except Exception:
            return text


def render_banner(
    *,
    console: Any | None = None,
    version: str = "0.3.0",
    mode: str = "TELEGRAM_ONLY",
    paper: bool = True,
    live_locked: bool = True,
    subtitle: str | None = None,
) -> None:
    """Print a full-width classy startup banner to the terminal."""
    if Console is None:
        print("BANGZEN PRIME", version, file=sys.stderr)
        return

    # Decorative output goes to stderr by default so machine-readable stdout stays clean.
    c = console or Console(stderr=True)
    art = _figlet("BANGZEN", font="slant")
    art2 = _figlet("PRIME", font="slant")

    title = Text()
    for line in art.splitlines():
        title.append(line + "\n", style=f"bold {GOLD}")
    for line in art2.splitlines():
        title.append(line + "\n", style=f"bold {CYAN}")

    meta = Table.grid(padding=(0, 2))
    meta.add_column(style=MUTED, justify="right")
    meta.add_column(style=IVORY)
    meta.add_row("VERSION", f"v{version}")
    meta.add_row("MODE", mode)
    meta.add_row("PAPER", "ENABLED" if paper else "OFF")
    meta.add_row(
        "LIVE CHAIN",
        (
            Text("LOCKED", style=f"bold {EMERALD}")
            if live_locked
            else Text("UNLOCKED", style=f"bold {CRIMSON}")
        ),
    )
    meta.add_row("UTC", datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"))
    if subtitle:
        meta.add_row("NOTE", subtitle)

    badge = Text()
    badge.append("  ◆  ", style=GOLD)
    badge.append("SOLANA INTELLIGENCE", style=f"bold {IVORY}")
    badge.append("  ·  ", style=MUTED)
    badge.append("SIGNAL & PAPER RESEARCH", style=CYAN)
    badge.append("  ·  ", style=MUTED)
    badge.append("FAIL-CLOSED", style=EMERALD)
    badge.append("  ◆  ", style=GOLD)

    body = Group(
        Align.center(title),
        Align.center(badge),
        Rule(style=GOLD_DIM),
        Align.center(meta),
    )

    panel = Panel(
        body,
        title=f"[bold {GOLD}]▸ BANGZEN PRIME[/]",
        subtitle=f"[{MUTED}]evidence-driven · paper-first[/{MUTED}]",
        border_style=GOLD,
        box=box.DOUBLE_EDGE,
        padding=(1, 2),
    )
    c.print(panel)


def render_compact_header(
    *,
    version: str = "0.3.0",
    mode: str = "TELEGRAM_ONLY",
) -> Panel:
    """Compact header panel for Live dashboard layouts."""
    if Console is None:
        raise RuntimeError("rich is required for dashboard header")

    left = Text()
    if pyfiglet is not None:
        small = _figlet("BZ", font="small")
        for i, line in enumerate(small.splitlines()[:4]):
            left.append(line + ("\n" if i < 3 else ""), style=f"bold {GOLD}")
    else:
        left.append("BANGZEN PRIME", style=f"bold {GOLD}")

    right = Table.grid(expand=True)
    right.add_column(justify="left")
    right.add_row(Text("BANGZEN PRIME", style=f"bold {GOLD}"))
    right.add_row(Text("Autonomous Solana Intelligence", style=MUTED))
    right.add_row(Text(f"v{version}  ·  {mode}  ·  LIVE LOCKED", style=CYAN))
    right.add_row(
        Text(datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC"), style=MUTED)
    )

    grid = Table.grid(expand=True, padding=(0, 2))
    grid.add_column(ratio=1)
    grid.add_column(ratio=3)
    grid.add_row(left, right)

    return Panel(
        grid,
        border_style=GOLD,
        box=box.HEAVY,
        title=f"[bold {IVORY}] COMMAND DECK [/]",
        subtitle=f"[{MUTED}]paper research · no broadcast[/{MUTED}]",
    )


if __name__ == "__main__":
    render_banner(version="0.3.0", mode="TELEGRAM_ONLY", paper=True, live_locked=True)
