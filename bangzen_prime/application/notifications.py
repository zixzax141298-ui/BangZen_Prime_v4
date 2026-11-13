"""Notification handler: formats accepted signals and delivers via the Notifier port."""

from __future__ import annotations
from decimal import Decimal, InvalidOperation

from bangzen_prime.application.ports import Notifier
from bangzen_prime.application.mode_controller import ModeController
from bangzen_prime.domain.shared import DomainEvent

SIGNAL_EVENT = "SignalGenerated"
SUBSCRIBER_NAME = "notify.signal"


def _fmt_price(value) -> str:
    """Memformat harga koin (mendukung koin mikro seperti BONK)."""
    try:
        d = Decimal(str(value))
        if d == 0:
            return "0"
        if abs(d) < Decimal("0.001"):
            return f"{d:.8f}".rstrip('0').rstrip('.')
        return f"{d:.4f}".rstrip('0').rstrip('.')
    except (InvalidOperation, ValueError):
        return str(value)


def _fmt_pct(value) -> str:
    """Memformat persentase/confidence (2 desimal)."""
    try:
        return f"{Decimal(str(value)):.2f}"
    except (InvalidOperation, ValueError):
        return str(value)


def format_signal_text(event: DomainEvent) -> str:
    p = event.payload
    lines = [
        "[SIGNAL ONLY | PAPER] Research alert; not a trade instruction.",
        f"Signal: {p.get('signal_id', 'UNAVAILABLE')}",
    ]
    if p.get("mint") and p.get("chain") and p.get("symbol"):
        lines.extend([
            f"Asset: {p['symbol']} ({p['chain']})",
            f"Mint: {p['mint']}",
            f"Pair: {p.get('pair_address', 'UNAVAILABLE')}",
            f"DEX: {p.get('dex_id', 'UNAVAILABLE')}",
            f"Market source: {p.get('market_source', 'UNAVAILABLE')}",
            f"Observed at: {p.get('market_observed_at', 'UNAVAILABLE')}",
        ])
    else:
        lines.append(f"Token id: {p.get('token_id', 'UNAVAILABLE')} (mint unavailable)")
    lines.extend([
        f"Entry reference: {_fmt_price(p.get('entry', 'UNAVAILABLE'))}",
        f"Stop reference: {_fmt_price(p.get('stop_loss', 'UNAVAILABLE'))}",
        f"Target reference: {_fmt_price(p.get('take_profit', 'UNAVAILABLE'))}",
        f"Heuristic score: {_fmt_pct(p.get('score', 'UNAVAILABLE'))}",
        f"Heuristic confidence: {_fmt_pct(p.get('confidence', 'UNAVAILABLE'))}",
    ])
    return "\n".join(lines)


def make_notification_handler(notifier: Notifier):
    def handle(event: DomainEvent) -> None:
        notifier.send(format_signal_text(event))  # raises on failure, so it is retried
    return handle


class LogNotifier:
    """Default adapter: writes to the structured log. Safe for offline use."""

    def __init__(self, logger) -> None:
        self._logger = logger

    def send(self, text: str) -> None:
        self._logger.info(text)


class ModeGatedNotifier:
    """Suppress signal delivery when the selected operating mode disables Telegram."""

    def __init__(self, notifier: Notifier, mode_controller: ModeController) -> None:
        self._notifier = notifier
        self._mode_controller = mode_controller

    def send(self, text: str) -> None:
        if self._mode_controller.snapshot().telegram_enabled:
            self._notifier.send(text)
